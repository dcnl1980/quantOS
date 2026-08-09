"""Authenticated venue broker protocol (testnet / live)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

from ..orders import Order
from ..reconciliation import VenueOrderReport


@dataclass(slots=True)
class PlaceResult:
    ok: bool
    venue_order_id: str | None = None
    reason: str = ""
    fill_qty: float = 0.0
    fill_price: float = 0.0
    fee: float = 0.0


@dataclass(slots=True)
class CancelResult:
    ok: bool
    reason: str = ""


@dataclass(slots=True)
class ReplaceResult:
    ok: bool
    new_venue_order_id: str | None = None
    reason: str = ""


@dataclass(slots=True)
class UserStreamEvent:
    type: str  # order_update | fill | balance
    venue: str
    payload: dict[str, Any] = field(default_factory=dict)


class VenueBroker(Protocol):
    venue: str
    authenticated: bool

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def place(self, order: Order) -> PlaceResult: ...
    async def cancel(self, order: Order) -> CancelResult: ...
    async def replace(self, order: Order, new_order: Order) -> ReplaceResult: ...
    async def open_orders(self) -> list[VenueOrderReport]: ...
    def user_stream(self) -> AsyncIterator[UserStreamEvent]: ...
