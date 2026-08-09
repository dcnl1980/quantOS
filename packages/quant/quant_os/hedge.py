"""Partial-fill hedge policy for paired cross-venue execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .orders import Order, OrderState


class HedgeAction(StrEnum):
    NONE = "none"
    WAIT = "wait"
    REDUCE_OTHER = "reduce_other"
    HEDGE_RESIDUAL = "hedge_residual"
    CANCEL_BOTH = "cancel_both"
    COMPLETE = "complete"


@dataclass(slots=True)
class HedgeDecision:
    action: HedgeAction
    reason: str
    hedge_qty: float = 0.0
    target_venue: str | None = None
    target_side: str | None = None


@dataclass
class PartialFillHedgePolicy:
    """
    For a buy-leg / sell-leg arb pair:
    - if both filled equally -> complete
    - if imbalance below min_hedge_qty -> wait for more fills
    - if one leg done and other lagging -> reduce/cancel lagging or hedge residual
    """

    min_hedge_qty: float = 1e-6
    max_imbalance_wait_fills: int = 2

    def evaluate(self, buy: Order, sell: Order) -> HedgeDecision:
        buy_filled = buy.filled_qty
        sell_filled = sell.filled_qty
        imbalance = buy_filled - sell_filled

        if buy.state == OrderState.FILLED and sell.state == OrderState.FILLED:
            if abs(imbalance) <= self.min_hedge_qty:
                return HedgeDecision(HedgeAction.COMPLETE, "both_legs_filled")
            # Residual inventory after both terminal.
            if imbalance > 0:
                return HedgeDecision(
                    HedgeAction.HEDGE_RESIDUAL,
                    "sell_shortfall_after_fill",
                    hedge_qty=imbalance,
                    target_venue=sell.venue,
                    target_side="sell",
                )
            return HedgeDecision(
                HedgeAction.HEDGE_RESIDUAL,
                "buy_shortfall_after_fill",
                hedge_qty=abs(imbalance),
                target_venue=buy.venue,
                target_side="buy",
            )

        if abs(imbalance) <= self.min_hedge_qty:
            if buy.is_terminal and sell.is_terminal:
                return HedgeDecision(HedgeAction.COMPLETE, "balanced_terminal")
            if buy.filled_qty > 0 and sell.filled_qty > 0:
                # Balanced partials: cancel residuals and lock in the paired trade.
                return HedgeDecision(HedgeAction.CANCEL_BOTH, "balanced_partial_cancel_residuals")
            return HedgeDecision(HedgeAction.WAIT, "balanced_in_flight")

        # One side significantly ahead.
        if buy_filled > sell_filled:
            if sell.is_terminal:
                return HedgeDecision(
                    HedgeAction.HEDGE_RESIDUAL,
                    "sell_leg_done_buy_heavy",
                    hedge_qty=imbalance,
                    target_venue=sell.venue,
                    target_side="sell",
                )
            if buy.is_terminal:
                return HedgeDecision(
                    HedgeAction.REDUCE_OTHER,
                    "buy_done_reduce_sell",
                    hedge_qty=sell.remaining,
                    target_venue=sell.venue,
                    target_side="sell",
                )
            return HedgeDecision(HedgeAction.WAIT, "buy_ahead_waiting_sell")

        # sell ahead
        if buy.is_terminal:
            return HedgeDecision(
                HedgeAction.HEDGE_RESIDUAL,
                "buy_leg_done_sell_heavy",
                hedge_qty=abs(imbalance),
                target_venue=buy.venue,
                target_side="buy",
            )
        if sell.is_terminal:
            return HedgeDecision(
                HedgeAction.REDUCE_OTHER,
                "sell_done_reduce_buy",
                hedge_qty=buy.remaining,
                target_venue=buy.venue,
                target_side="buy",
            )
        return HedgeDecision(HedgeAction.WAIT, "sell_ahead_waiting_buy")
