"""Deterministic simulated venue testnet with partial fills and user streams."""
from __future__ import annotations

import asyncio
import itertools
import uuid
from collections import defaultdict
from typing import AsyncIterator

from ..models import Side
from ..orders import Order
from ..reconciliation import VenueOrderReport
from .base import CancelResult, PlaceResult, ReplaceResult, UserStreamEvent


class SimulatedTestnetBroker:
    """
    Auth-gated simulated testnet. Supports IOC-like partial fills, cancel/replace,
    and an in-process user/order stream.
    """

    def __init__(
        self,
        venue: str,
        api_key: str = "testnet",
        api_secret: str = "testnet",
        partial_fill_ratio: float = 0.6,
        fill_slippage_bps: float = 2.0,
        taker_fee_bps: float = 10.0,
        require_auth: bool = True,
    ):
        self.venue = venue
        self.api_key = api_key
        self.api_secret = api_secret
        self.partial_fill_ratio = max(0.0, min(1.0, partial_fill_ratio))
        self.fill_slippage_bps = fill_slippage_bps
        self.taker_fee_bps = taker_fee_bps
        self.require_auth = require_auth
        self.authenticated = False
        self._ids = itertools.count(1)
        self._orders: dict[str, Order] = {}
        self._cancelled: set[str] = set()
        self._venue_to_client: dict[str, str] = {}
        self._events: asyncio.Queue[UserStreamEvent] = asyncio.Queue()
        self._balances: dict[str, float] = defaultdict(lambda: 100000.0)

    async def connect(self) -> None:
        if self.require_auth and (not self.api_key or not self.api_secret):
            raise PermissionError(f"{self.venue}: missing testnet credentials")
        self.authenticated = True
        await self._emit("balance", {"balances": dict(self._balances)})

    async def close(self) -> None:
        self.authenticated = False

    async def place(self, order: Order) -> PlaceResult:
        self._ensure_auth()
        if order.client_order_id in self._orders:
            # Idempotent retry.
            existing = self._orders[order.client_order_id]
            return PlaceResult(
                True,
                existing.venue_order_id,
                "idempotent_replay",
                existing.filled_qty,
                existing.avg_fill_price,
                existing.fee,
            )
        if order.quantity <= 0 or order.price <= 0:
            return PlaceResult(False, reason="invalid_quantity_or_price")

        venue_order_id = f"{self.venue}-{next(self._ids)}"
        slip = self.fill_slippage_bps / 10000.0
        px = order.price * (1 + slip if order.side == Side.BUY else 1 - slip)
        fill_qty = order.quantity * self.partial_fill_ratio
        # Tiny residuals round to full fill for determinism.
        if order.quantity - fill_qty < 1e-8:
            fill_qty = order.quantity
        fee = fill_qty * px * self.taker_fee_bps / 10000.0

        stored = Order(
            venue=order.venue,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            strategy=order.strategy,
            opportunity_id=order.opportunity_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            filled_qty=fill_qty,
            avg_fill_price=px if fill_qty else 0.0,
            fee=fee,
        )
        self._orders[order.client_order_id] = stored
        self._venue_to_client[venue_order_id] = order.client_order_id
        await self._emit("order_update", stored.to_dict() | {"event": "accepted"})
        if fill_qty > 0:
            await self._emit(
                "fill",
                {
                    "client_order_id": order.client_order_id,
                    "venue_order_id": venue_order_id,
                    "qty": fill_qty,
                    "price": px,
                    "fee": fee,
                    "symbol": order.symbol,
                    "side": order.side.value,
                },
            )
        return PlaceResult(True, venue_order_id, "accepted", fill_qty, px, fee)

    async def cancel(self, order: Order) -> CancelResult:
        self._ensure_auth()
        stored = self._orders.get(order.client_order_id)
        if not stored:
            return CancelResult(False, "unknown_order")
        if stored.filled_qty + 1e-12 >= stored.quantity:
            return CancelResult(False, "already_filled")
        stored.quantity = stored.filled_qty  # cancel residual
        self._cancelled.add(order.client_order_id)
        await self._emit("order_update", stored.to_dict() | {"event": "cancelled"})
        return CancelResult(True, "cancelled")

    async def replace(self, order: Order, new_order: Order) -> ReplaceResult:
        self._ensure_auth()
        cancel = await self.cancel(order)
        if not cancel.ok and cancel.reason != "already_filled":
            return ReplaceResult(False, reason=cancel.reason)
        # Preserve remaining quantity semantics.
        remaining = max(0.0, order.quantity - order.filled_qty)
        if remaining <= 0:
            return ReplaceResult(False, reason="nothing_to_replace")
        new_order.quantity = min(new_order.quantity, remaining) if new_order.quantity else remaining
        placed = await self.place(new_order)
        if not placed.ok:
            return ReplaceResult(False, reason=placed.reason)
        return ReplaceResult(True, placed.venue_order_id, "replaced")

    async def open_orders(self) -> list[VenueOrderReport]:
        self._ensure_auth()
        out = []
        for o in self._orders.values():
            if o.client_order_id in self._cancelled:
                state = "cancelled"
            elif o.filled_qty + 1e-12 >= o.quantity:
                state = "filled"
            elif o.filled_qty > 0:
                state = "partially_filled"
            else:
                state = "accepted"
            out.append(VenueOrderReport(
                client_order_id=o.client_order_id,
                venue_order_id=o.venue_order_id or "",
                state=state,
                filled_qty=o.filled_qty,
                avg_fill_price=o.avg_fill_price,
                fee=o.fee,
            ))
        return out

    async def user_stream(self) -> AsyncIterator[UserStreamEvent]:
        self._ensure_auth()
        while self.authenticated:
            try:
                event = await asyncio.wait_for(self._events.get(), timeout=0.25)
                yield event
            except asyncio.TimeoutError:
                continue

    async def force_fill_remainder(self, client_order_id: str) -> PlaceResult:
        """Test helper: fill any residual quantity."""
        stored = self._orders[client_order_id]
        rem = stored.quantity - stored.filled_qty
        if rem <= 0:
            return PlaceResult(True, stored.venue_order_id, "already_filled")
        px = stored.avg_fill_price or stored.price
        fee = rem * px * self.taker_fee_bps / 10000.0
        stored.filled_qty = stored.quantity
        stored.fee += fee
        await self._emit(
            "fill",
            {
                "client_order_id": client_order_id,
                "venue_order_id": stored.venue_order_id,
                "qty": rem,
                "price": px,
                "fee": fee,
                "symbol": stored.symbol,
                "side": stored.side.value,
            },
        )
        return PlaceResult(True, stored.venue_order_id, "remainder_filled", rem, px, fee)

    def _ensure_auth(self):
        if not self.authenticated:
            raise PermissionError(f"{self.venue}: broker not connected")

    async def _emit(self, type_: str, payload: dict):
        await self._events.put(UserStreamEvent(type_, self.venue, payload))
