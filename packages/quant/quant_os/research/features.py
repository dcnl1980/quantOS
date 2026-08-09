"""Lightweight in-process feature store for research features."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

from quant_os.models import Quote, utcnow


@dataclass
class FeatureRecord:
    name: str
    symbol: str
    value: float
    ts: datetime
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "value": self.value,
            "ts": self.ts.isoformat(),
            "tags": self.tags,
        }


class FeatureStore:
    def __init__(self, maxlen: int = 5000):
        self.maxlen = maxlen
        self._series: dict[tuple[str, str], deque[FeatureRecord]] = defaultdict(
            lambda: deque(maxlen=self.maxlen)
        )
        self.computed = 0

    def put(self, name: str, symbol: str, value: float, **tags):
        rec = FeatureRecord(name, symbol, float(value), utcnow(), tags)
        self._series[(name, symbol)].append(rec)
        self.computed += 1
        return rec

    def latest(self, name: str, symbol: str) -> FeatureRecord | None:
        q = self._series.get((name, symbol))
        return q[-1] if q else None

    def history(self, name: str, symbol: str, n: int = 100) -> list[FeatureRecord]:
        q = self._series.get((name, symbol), deque())
        return list(q)[-n:]

    def ingest_quotes(self, quotes: list[Quote]) -> dict[str, float]:
        """Derive cross-venue research features from a quote batch."""
        if len(quotes) < 2:
            return {}
        symbol = quotes[0].symbol
        mids = [q.mid for q in quotes if q.mid > 0]
        spreads = [q.spread_bps for q in quotes]
        best_ask = min(quotes, key=lambda q: q.ask)
        best_bid = max(quotes, key=lambda q: q.bid)
        gross = ((best_bid.bid - best_ask.ask) / best_ask.ask) * 10000 if best_ask.ask > 0 else 0.0
        feats = {
            "mid_mean": mean(mids) if mids else 0.0,
            "mid_dispersion_bps": (pstdev(mids) / mean(mids) * 10000) if len(mids) > 1 and mean(mids) else 0.0,
            "avg_spread_bps": mean(spreads) if spreads else 0.0,
            "cross_venue_gross_bps": gross,
            "venue_count": float(len(quotes)),
        }
        for name, value in feats.items():
            self.put(name, symbol, value, source="quote_batch")
        return feats

    def ingest_dataset(self, batches: list[list[Quote]], max_batches: int | None = None) -> int:
        count = 0
        for batch in batches[: max_batches or len(batches)]:
            self.ingest_quotes(batch)
            count += 1
        return count

    def snapshot(self) -> dict:
        keys = sorted(self._series)
        return {
            "series": len(keys),
            "computed": self.computed,
            "features": [
                {
                    "name": name,
                    "symbol": symbol,
                    "points": len(self._series[(name, symbol)]),
                    "latest": self.latest(name, symbol).to_dict() if self.latest(name, symbol) else None,
                }
                for name, symbol in keys
            ],
        }
