"""H2 execution gateway: testnet routing, hedge policy, user streams, reconciliation."""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import asdict
from typing import Any, Callable, Awaitable

from quant_os.models import Side, Fill, Opportunity
from quant_os.orders import Order, OrderStateMachine, OrderState
from quant_os.hedge import PartialFillHedgePolicy, HedgeAction
from quant_os.inventory import InventoryAllocator
from quant_os.fee_tiers import FeeSchedule
from quant_os.reconciliation import Reconciler
from quant_os.venues import SimulatedTestnetBroker
from quant_os.risk import RiskEngine

log = logging.getLogger("quant.execution.gateway")


class ExecutionGateway:
    def __init__(
        self,
        risk: RiskEngine,
        fee_schedule: FeeSchedule,
        inventory: InventoryAllocator,
        publish: Callable[[dict[str, Any]], Awaitable[None]],
        hedge: PartialFillHedgePolicy | None = None,
        partial_fill_ratio: float = 0.65,
    ):
        self.risk = risk
        self.fees = fee_schedule
        self.inventory = inventory
        self.publish = publish
        self.hedge = hedge or PartialFillHedgePolicy()
        self.fsm = OrderStateMachine()
        self.reconciler = Reconciler(self.fsm)
        self.brokers: dict[str, SimulatedTestnetBroker] = {}
        self.partial_fill_ratio = partial_fill_ratio
        self.tasks: list[asyncio.Task] = []
        self.trade_count = 0
        self.hedge_count = 0
        self.fills: deque[Fill] = deque(maxlen=2000)
        self.sessions: deque[dict[str, Any]] = deque(maxlen=200)
        self._pair_legs: dict[str, tuple[str, str]] = {}  # opportunity_id -> (buy_cid, sell_cid)
        self._lock = asyncio.Lock()

    def attach_broker(self, broker: SimulatedTestnetBroker):
        self.brokers[broker.venue] = broker

    async def start(self, venues: list[str], api_key: str, api_secret: str):
        for venue in venues:
            if venue not in self.brokers:
                self.brokers[venue] = SimulatedTestnetBroker(
                    venue=venue,
                    api_key=api_key or "testnet",
                    api_secret=api_secret or "testnet",
                    partial_fill_ratio=self.partial_fill_ratio,
                    taker_fee_bps=self.fees.taker_bps(venue),
                )
            await self.brokers[venue].connect()
            self.tasks.append(asyncio.create_task(self._pump_user_stream(venue)))
        self.tasks.append(asyncio.create_task(self._recon_loop()))

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        for b in self.brokers.values():
            await b.close()

    async def execute_arbitrage(
        self,
        op: Opportunity,
        portfolio,
        desired_notional: float,
        strategy: str = "cross_venue_arbitrage",
    ) -> dict[str, Any]:
        async with self._lock:
            return await self._execute_arbitrage_locked(op, portfolio, desired_notional, strategy)

    async def _execute_arbitrage_locked(
        self,
        op: Opportunity,
        portfolio,
        desired_notional: float,
        strategy: str,
    ) -> dict[str, Any]:
        decision = self.risk.evaluate(
            op, portfolio, desired_notional, estimated_slippage_bps=2.0
        )
        await self.publish({
            "type": "risk_decision",
            "data": {
                "opportunity_id": op.id,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "approved_notional": decision.approved_notional,
                "engine": "testnet-gateway",
                "execution_mode": "testnet",
            },
        })
        if not decision.allowed:
            return {"ok": False, "reason": decision.reason}

        buy_alloc = self.inventory.allocate(op.buy_venue, decision.approved_notional)
        sell_alloc = self.inventory.allocate(op.sell_venue, decision.approved_notional)
        approved = min(buy_alloc, sell_alloc)
        if approved <= 0:
            self.inventory.release(op.buy_venue, buy_alloc)
            self.inventory.release(op.sell_venue, sell_alloc)
            return {"ok": False, "reason": "insufficient_venue_inventory_capacity"}

        qty = approved / op.buy_price
        buy = Order(
            venue=op.buy_venue, symbol=op.symbol, side=Side.BUY, quantity=qty,
            price=op.buy_price, strategy=strategy, opportunity_id=op.id,
        )
        sell = Order(
            venue=op.sell_venue, symbol=op.symbol, side=Side.SELL, quantity=qty,
            price=op.sell_price, strategy=strategy, opportunity_id=op.id,
        )
        self.fsm.register(buy)
        self.fsm.register(sell)
        self._pair_legs[op.id] = (buy.client_order_id, sell.client_order_id)

        buy_broker = self._broker(op.buy_venue)
        sell_broker = self._broker(op.sell_venue)
        buy_res, sell_res = await asyncio.gather(buy_broker.place(buy), sell_broker.place(sell))

        if not buy_res.ok:
            self.fsm.reject(buy.client_order_id, buy_res.reason)
        else:
            self.fsm.accept(buy.client_order_id, buy_res.venue_order_id or "")
            if buy_res.fill_qty > 0:
                self.fsm.apply_fill(buy.client_order_id, buy_res.fill_qty, buy_res.fill_price, buy_res.fee)
                await self._on_fill(buy, buy_res.fill_qty, buy_res.fill_price, buy_res.fee)

        if not sell_res.ok:
            self.fsm.reject(sell.client_order_id, sell_res.reason)
        else:
            self.fsm.accept(sell.client_order_id, sell_res.venue_order_id or "")
            if sell_res.fill_qty > 0:
                self.fsm.apply_fill(sell.client_order_id, sell_res.fill_qty, sell_res.fill_price, sell_res.fee)
                await self._on_fill(sell, sell_res.fill_qty, sell_res.fill_price, sell_res.fee)

        # Refresh local order objects
        buy = self.fsm.get(buy.client_order_id)
        sell = self.fsm.get(sell.client_order_id)
        assert buy and sell
        hedge = await self._apply_hedge(buy, sell)
        buy = self.fsm.get(buy.client_order_id)
        sell = self.fsm.get(sell.client_order_id)
        assert buy and sell
        session = {
            "opportunity_id": op.id,
            "symbol": op.symbol,
            "buy": buy.to_dict(),
            "sell": sell.to_dict(),
            "hedge": {
                "action": hedge.action.value,
                "reason": hedge.reason,
                "hedge_qty": hedge.hedge_qty,
            },
            "approved_notional": approved,
        }
        self.sessions.appendleft(session)
        paired = buy.filled_qty > 0 and sell.filled_qty > 0 and abs(buy.filled_qty - sell.filled_qty) <= 1e-8
        if paired and (buy.is_terminal and sell.is_terminal):
            self.trade_count += 1
        await self.publish({"type": "execution_session", "data": session})
        return {"ok": True, "session": session}

    async def cancel_order(self, client_order_id: str) -> dict:
        order = self.fsm.get(client_order_id)
        if not order:
            return {"ok": False, "reason": "unknown_order"}
        self.fsm.request_cancel(client_order_id)
        res = await self._broker(order.venue).cancel(order)
        if res.ok:
            self.fsm.confirm_cancel(client_order_id)
            self.inventory.release(order.venue, order.remaining * order.price)
        await self.publish({
            "type": "order_cancel",
            "data": {"client_order_id": client_order_id, "ok": res.ok, "reason": res.reason},
        })
        return {"ok": res.ok, "reason": res.reason, "order": self.fsm.get(client_order_id).to_dict()}

    async def replace_order(self, client_order_id: str, new_price: float, new_qty: float | None = None) -> dict:
        order = self.fsm.get(client_order_id)
        if not order:
            return {"ok": False, "reason": "unknown_order"}
        replacement = Order(
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=new_qty if new_qty is not None else order.remaining,
            price=new_price,
            strategy=order.strategy,
            opportunity_id=order.opportunity_id,
        )
        self.fsm.request_replace(client_order_id, replacement)
        res = await self._broker(order.venue).replace(order, replacement)
        if res.ok:
            self.fsm.accept(replacement.client_order_id, res.new_venue_order_id or "")
            self.fsm.confirm_replace(client_order_id)
            if res:  # place already may have partial filled via broker.replace -> place
                placed = await self._broker(order.venue).open_orders()
                for report in placed:
                    if report.client_order_id == replacement.client_order_id and report.filled_qty > 0:
                        self.fsm.apply_fill(
                            replacement.client_order_id,
                            report.filled_qty,
                            report.avg_fill_price,
                            report.fee,
                        )
        await self.publish({
            "type": "order_replace",
            "data": {
                "old": client_order_id,
                "new": replacement.client_order_id,
                "ok": res.ok,
                "reason": res.reason,
            },
        })
        return {
            "ok": res.ok,
            "reason": res.reason,
            "old": self.fsm.get(client_order_id).to_dict() if self.fsm.get(client_order_id) else None,
            "new": self.fsm.get(replacement.client_order_id).to_dict() if self.fsm.get(replacement.client_order_id) else None,
        }

    async def _apply_hedge(self, buy: Order, sell: Order):
        decision = self.hedge.evaluate(buy, sell)
        if decision.action == HedgeAction.WAIT:
            return decision
        if decision.action == HedgeAction.COMPLETE:
            return decision
        if decision.action == HedgeAction.REDUCE_OTHER:
            target_id = buy.client_order_id if decision.target_side == "buy" else sell.client_order_id
            await self.cancel_order(target_id)
            self.hedge_count += 1
            return decision
        if decision.action == HedgeAction.HEDGE_RESIDUAL and decision.hedge_qty > 0:
            side = Side.BUY if decision.target_side == "buy" else Side.SELL
            venue = decision.target_venue or (buy.venue if side == Side.BUY else sell.venue)
            px = buy.price if side == Side.BUY else sell.price
            hedge_order = Order(
                venue=venue,
                symbol=buy.symbol,
                side=side,
                quantity=decision.hedge_qty,
                price=px,
                strategy="partial_fill_hedge",
                opportunity_id=buy.opportunity_id,
            )
            self.fsm.register(hedge_order)
            res = await self._broker(venue).place(hedge_order)
            if res.ok:
                self.fsm.accept(hedge_order.client_order_id, res.venue_order_id or "")
                if res.fill_qty > 0:
                    self.fsm.apply_fill(
                        hedge_order.client_order_id, res.fill_qty, res.fill_price, res.fee
                    )
                    await self._on_fill(hedge_order, res.fill_qty, res.fill_price, res.fee)
                self.hedge_count += 1
            await self.publish({
                "type": "hedge",
                "data": {
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "order": hedge_order.to_dict(),
                    "result": asdict(res) if hasattr(res, "__dataclass_fields__") else {
                        "ok": res.ok, "reason": res.reason,
                        "fill_qty": res.fill_qty, "fill_price": res.fill_price,
                    },
                },
            })
        if decision.action == HedgeAction.CANCEL_BOTH:
            if not buy.is_terminal:
                await self.cancel_order(buy.client_order_id)
            if not sell.is_terminal:
                await self.cancel_order(sell.client_order_id)
            self.hedge_count += 1
        return decision

    async def _on_fill(self, order: Order, qty: float, price: float, fee: float):
        signed = qty if order.side == Side.BUY else -qty
        self.inventory.apply_fill(order.venue, order.symbol, signed, qty * price)
        self.fees.record_notional(order.venue, qty * price)
        fill = Fill(
            order_id=order.client_order_id,
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            fee=fee,
            strategy=order.strategy,
            opportunity_id=order.opportunity_id,
            id=str(uuid.uuid4()),
        )
        self.fills.append(fill)
        fd = fill.to_dict()
        fd["client_order_id"] = order.client_order_id
        fd["execution_mode"] = "testnet"
        await self.publish({"type": "fill", "data": fd})

    async def _pump_user_stream(self, venue: str):
        broker = self.brokers[venue]
        try:
            async for event in broker.user_stream():
                await self.publish({
                    "type": "user_stream",
                    "data": {"venue": venue, "event_type": event.type, "payload": event.payload},
                })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("user stream %s stopped: %s", venue, exc)

    async def _recon_loop(self):
        try:
            while True:
                await asyncio.sleep(1.0)
                await self.reconcile_once()
        except asyncio.CancelledError:
            raise

    async def reconcile_once(self) -> dict:
        async with self._lock:
            reports = []
            for broker in self.brokers.values():
                try:
                    reports.extend(await broker.open_orders())
                except Exception as exc:
                    log.debug("recon fetch failed: %s", exc)
            result = self.reconciler.reconcile(reports)
        await self.publish({"type": "reconciliation", "data": result})
        return result

    def _broker(self, venue: str) -> SimulatedTestnetBroker:
        if venue not in self.brokers:
            raise KeyError(f"no testnet broker for venue {venue}")
        return self.brokers[venue]

    def snapshot(self) -> dict[str, Any]:
        return {
            "brokers": {
                v: {"authenticated": b.authenticated, "venue": b.venue}
                for v, b in self.brokers.items()
            },
            "orders": self.fsm.snapshot(),
            "inventory": self.inventory.to_dict(),
            "fees": self.fees.to_dict(),
            "reconciliation": self.reconciler.to_dict(),
            "trade_count": self.trade_count,
            "hedge_count": self.hedge_count,
            "fills": [f.to_dict() for f in list(self.fills)[-50:]][::-1],
            "sessions": list(self.sessions)[:20],
        }
