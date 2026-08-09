"""Idempotent order state machine with cancel/replace support."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import StrEnum
from typing import Any

from .models import Side, utcnow


class OrderState(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REPLACE_PENDING = "replace_pending"
    REPLACED = "replaced"
    REJECTED = "rejected"


_TERMINAL = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REPLACED, OrderState.REJECTED}

# Legal transitions for the venue-facing order FSM.
_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.NEW: {OrderState.ACCEPTED, OrderState.REJECTED},
    OrderState.ACCEPTED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.REPLACE_PENDING,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.REPLACE_PENDING,
        OrderState.CANCELLED,
    },
    OrderState.CANCEL_PENDING: {OrderState.CANCELLED, OrderState.FILLED, OrderState.PARTIALLY_FILLED},
    OrderState.REPLACE_PENDING: {
        OrderState.REPLACED,
        OrderState.FILLED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCELLED,
    },
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REPLACED: set(),
    OrderState.REJECTED: set(),
}


def make_client_order_id(prefix: str = "q") -> str:
    # Venue-safe short idempotency key.
    return f"{prefix}{uuid.uuid4().hex[:24]}"


@dataclass(slots=True)
class Order:
    venue: str
    symbol: str
    side: Side
    quantity: float
    price: float
    strategy: str
    opportunity_id: str | None = None
    client_order_id: str = field(default_factory=make_client_order_id)
    venue_order_id: str | None = None
    state: OrderState = OrderState.NEW
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    fee: float = 0.0
    reject_reason: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    replaces_client_order_id: str | None = None
    replaced_by_client_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled_qty)

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["state"] = self.state.value
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        d["remaining"] = self.remaining
        return d


class OrderTransitionError(RuntimeError):
    pass


class OrderStateMachine:
    """Tracks orders by client_order_id with idempotent updates."""

    def __init__(self):
        self.orders: dict[str, Order] = {}
        self.by_venue_id: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []

    def register(self, order: Order) -> Order:
        existing = self.orders.get(order.client_order_id)
        if existing:
            return existing  # idempotent create
        self.orders[order.client_order_id] = order
        self._emit("order_registered", order)
        return order

    def get(self, client_order_id: str) -> Order | None:
        return self.orders.get(client_order_id)

    def transition(self, client_order_id: str, new_state: OrderState, **fields) -> Order:
        order = self.orders[client_order_id]
        allowed = _TRANSITIONS.get(order.state, set())
        if new_state != order.state and new_state not in allowed:
            raise OrderTransitionError(f"{order.state} -> {new_state} illegal")
        order.state = new_state
        for k, v in fields.items():
            if hasattr(order, k):
                setattr(order, k, v)
        order.updated_at = utcnow()
        if order.venue_order_id:
            self.by_venue_id[order.venue_order_id] = order.client_order_id
        self._emit("order_transition", order, to=new_state.value)
        return order

    def accept(self, client_order_id: str, venue_order_id: str) -> Order:
        return self.transition(
            client_order_id, OrderState.ACCEPTED, venue_order_id=venue_order_id
        )

    def reject(self, client_order_id: str, reason: str) -> Order:
        return self.transition(
            client_order_id, OrderState.REJECTED, reject_reason=reason
        )

    def apply_fill(self, client_order_id: str, qty: float, price: float, fee: float = 0.0) -> Order:
        order = self.orders[client_order_id]
        if order.is_terminal and order.state != OrderState.PARTIALLY_FILLED:
            if order.state == OrderState.FILLED:
                return order  # idempotent late fill ignore
            raise OrderTransitionError(f"cannot fill order in state {order.state}")
        fill_qty = min(qty, order.remaining)
        if fill_qty <= 0:
            return order
        total = order.filled_qty + fill_qty
        order.avg_fill_price = (
            (order.avg_fill_price * order.filled_qty + price * fill_qty) / total
            if total else 0.0
        )
        order.filled_qty = total
        order.fee += fee
        order.updated_at = utcnow()
        if order.filled_qty + 1e-12 >= order.quantity:
            return self.transition(client_order_id, OrderState.FILLED)
        return self.transition(client_order_id, OrderState.PARTIALLY_FILLED)

    def request_cancel(self, client_order_id: str) -> Order:
        return self.transition(client_order_id, OrderState.CANCEL_PENDING)

    def confirm_cancel(self, client_order_id: str) -> Order:
        return self.transition(client_order_id, OrderState.CANCELLED)

    def request_replace(self, client_order_id: str, new_order: Order) -> Order:
        old = self.transition(client_order_id, OrderState.REPLACE_PENDING)
        new_order.replaces_client_order_id = old.client_order_id
        self.register(new_order)
        old.replaced_by_client_order_id = new_order.client_order_id
        old.updated_at = utcnow()
        return new_order

    def confirm_replace(self, old_client_order_id: str) -> Order:
        return self.transition(old_client_order_id, OrderState.REPLACED)

    def open_orders(self, venue: str | None = None) -> list[Order]:
        out = []
        for o in self.orders.values():
            if o.is_terminal:
                continue
            if venue and o.venue != venue:
                continue
            out.append(o)
        return out

    def snapshot(self) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        for o in self.orders.values():
            by_state[o.state.value] = by_state.get(o.state.value, 0) + 1
        return {
            "orders": len(self.orders),
            "open": len(self.open_orders()),
            "by_state": by_state,
            "recent": [o.to_dict() for o in list(self.orders.values())[-20:]],
        }

    def _emit(self, event_type: str, order: Order, **extra):
        self.events.append({
            "type": event_type,
            "client_order_id": order.client_order_id,
            "state": order.state.value,
            "venue": order.venue,
            "symbol": order.symbol,
            **extra,
            "ts": utcnow().isoformat(),
        })
        if len(self.events) > 2000:
            self.events = self.events[-1000:]
