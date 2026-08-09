"""Full L2 order book with Binance-style sequence gap recovery."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable


class BookStatus(StrEnum):
    EMPTY = "empty"
    SYNCING = "syncing"
    LIVE = "live"
    STALE = "stale"
    GAP = "gap"


@dataclass(slots=True)
class BookLevel:
    price: float
    size: float


@dataclass(slots=True)
class BookUpdate:
    venue: str
    symbol: str
    first_update_id: int
    final_update_id: int
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    is_snapshot: bool = False
    prev_final_update_id: int | None = None


@dataclass
class OrderBook:
    venue: str
    symbol: str
    depth: int = 50
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_update_id: int | None = None
    status: BookStatus = BookStatus.EMPTY
    gap_count: int = 0
    applied_updates: int = 0
    buffered: list[BookUpdate] = field(default_factory=list)

    def best_bid(self) -> BookLevel | None:
        if not self.bids:
            return None
        price = max(self.bids)
        return BookLevel(price, self.bids[price])

    def best_ask(self) -> BookLevel | None:
        if not self.asks:
            return None
        price = min(self.asks)
        return BookLevel(price, self.asks[price])

    def mid(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if not bid or not ask:
            return None
        return (bid.price + ask.price) / 2

    def apply_snapshot(self, update_id: int, bids: Iterable[tuple[float, float]], asks: Iterable[tuple[float, float]]):
        self.bids = {p: s for p, s in bids if s > 0}
        self.asks = {p: s for p, s in asks if s > 0}
        self.last_update_id = update_id
        self.status = BookStatus.SYNCING
        self._trim()
        self._drain_buffer()

    def apply_update(self, update: BookUpdate) -> BookStatus:
        if update.is_snapshot:
            self.apply_snapshot(update.final_update_id, update.bids, update.asks)
            return self.status

        if self.last_update_id is None:
            self.buffered.append(update)
            self.status = BookStatus.SYNCING
            return self.status

        # Binance depth stream: drop events already covered by the snapshot.
        if update.final_update_id <= self.last_update_id:
            return self.status

        expected = self.last_update_id + 1
        if update.first_update_id > expected:
            self.gap_count += 1
            self.status = BookStatus.GAP
            self.buffered.append(update)
            return self.status

        self._mutate(update)
        self.last_update_id = update.final_update_id
        self.applied_updates += 1
        self.status = BookStatus.LIVE
        self._trim()
        return self.status

    def needs_resnapshot(self) -> bool:
        return self.status in {BookStatus.EMPTY, BookStatus.GAP, BookStatus.STALE}

    def mark_stale(self):
        self.status = BookStatus.STALE

    def top(self, n: int = 5) -> dict:
        bid_levels = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        ask_levels = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return {
            "venue": self.venue,
            "symbol": self.symbol,
            "status": self.status.value,
            "last_update_id": self.last_update_id,
            "gap_count": self.gap_count,
            "bids": [{"price": p, "size": s} for p, s in bid_levels],
            "asks": [{"price": p, "size": s} for p, s in ask_levels],
            "mid": self.mid(),
        }

    def _mutate(self, update: BookUpdate):
        for price, size in update.bids:
            if size <= 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size
        for price, size in update.asks:
            if size <= 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size

    def _drain_buffer(self):
        if self.last_update_id is None:
            return
        kept: list[BookUpdate] = []
        for update in sorted(self.buffered, key=lambda u: u.final_update_id):
            if update.final_update_id <= self.last_update_id:
                continue
            if update.first_update_id > self.last_update_id + 1:
                kept.append(update)
                self.status = BookStatus.GAP
                continue
            self._mutate(update)
            self.last_update_id = update.final_update_id
            self.applied_updates += 1
            self.status = BookStatus.LIVE
        self.buffered = kept
        self._trim()

    def _trim(self):
        if len(self.bids) > self.depth:
            for price, _ in sorted(self.bids.items(), key=lambda x: -x[0])[self.depth:]:
                self.bids.pop(price, None)
        if len(self.asks) > self.depth:
            for price, _ in sorted(self.asks.items(), key=lambda x: x[0])[self.depth:]:
                self.asks.pop(price, None)


class OrderBookRegistry:
    def __init__(self, depth: int = 50):
        self.depth = depth
        self.books: dict[tuple[str, str], OrderBook] = {}

    def get(self, venue: str, symbol: str) -> OrderBook:
        key = (venue, symbol)
        if key not in self.books:
            self.books[key] = OrderBook(venue, symbol, depth=self.depth)
        return self.books[key]

    def apply(self, update: BookUpdate) -> OrderBook:
        book = self.get(update.venue, update.symbol)
        book.apply_update(update)
        return book

    def snapshot(self) -> list[dict]:
        return [b.top() for b in self.books.values()]
