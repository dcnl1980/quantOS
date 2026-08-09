"""Per-venue inventory / capital allocator."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InventoryAllocator:
    total_capital: float
    venue_weights: dict[str, float] = field(default_factory=dict)
    reserved: dict[str, float] = field(default_factory=dict)
    inventory_qty: dict[str, dict[str, float]] = field(default_factory=dict)  # venue -> symbol -> qty

    def __post_init__(self):
        if not self.venue_weights:
            self.venue_weights = {"binance": 0.5, "coinbase": 0.5, "sim_a": 0.5, "sim_b": 0.5}
        self._normalize_weights()

    def _normalize_weights(self):
        total = sum(max(0.0, w) for w in self.venue_weights.values()) or 1.0
        self.venue_weights = {k: max(0.0, v) / total for k, v in self.venue_weights.items()}

    def set_weight(self, venue: str, weight: float):
        self.venue_weights[venue] = max(0.0, weight)
        self._normalize_weights()

    def capacity(self, venue: str) -> float:
        return self.total_capital * self.venue_weights.get(venue, 0.0)

    def available(self, venue: str) -> float:
        return max(0.0, self.capacity(venue) - self.reserved.get(venue, 0.0))

    def allocate(self, venue: str, notional: float) -> float:
        """Reserve capital; returns approved notional (may be clipped)."""
        approved = min(max(0.0, notional), self.available(venue))
        self.reserved[venue] = self.reserved.get(venue, 0.0) + approved
        return approved

    def release(self, venue: str, notional: float):
        self.reserved[venue] = max(0.0, self.reserved.get(venue, 0.0) - abs(notional))

    def apply_fill(self, venue: str, symbol: str, signed_qty: float, notional: float):
        bucket = self.inventory_qty.setdefault(venue, {})
        bucket[symbol] = bucket.get(symbol, 0.0) + signed_qty
        self.release(venue, notional)

    def position(self, venue: str, symbol: str) -> float:
        return self.inventory_qty.get(venue, {}).get(symbol, 0.0)

    def net_symbol(self, symbol: str) -> float:
        return sum(v.get(symbol, 0.0) for v in self.inventory_qty.values())

    def to_dict(self) -> dict:
        return {
            "total_capital": self.total_capital,
            "venue_weights": dict(self.venue_weights),
            "capacity": {v: self.capacity(v) for v in self.venue_weights},
            "available": {v: self.available(v) for v in self.venue_weights},
            "reserved": dict(self.reserved),
            "inventory_qty": {v: dict(q) for v, q in self.inventory_qty.items()},
        }
