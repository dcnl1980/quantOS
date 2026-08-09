"""Exchange vs local clock skew telemetry (NTP/PTP readiness signal)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median


def _to_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


@dataclass(slots=True)
class ClockSample:
    venue: str
    offset_ms: float
    observed_at: datetime


class ClockTelemetry:
    def __init__(self, window: int = 500, stale_ms: float = 250.0):
        self.window = window
        self.stale_ms = stale_ms
        self.samples: deque[ClockSample] = deque(maxlen=window)
        self.by_venue: dict[str, deque[float]] = {}

    def observe(self, venue: str, exchange_ts: datetime, received_ts: datetime | None = None) -> float:
        received = _to_aware(received_ts or datetime.now(timezone.utc))
        exchange = _to_aware(exchange_ts)
        offset_ms = (received - exchange).total_seconds() * 1000.0
        self.samples.append(ClockSample(venue, offset_ms, received))
        bucket = self.by_venue.setdefault(venue, deque(maxlen=self.window))
        bucket.append(offset_ms)
        return offset_ms

    def venue_stats(self, venue: str) -> dict:
        vals = list(self.by_venue.get(venue, []))
        if not vals:
            return {"venue": venue, "samples": 0, "median_offset_ms": 0.0, "p95_offset_ms": 0.0, "stale": False}
        ordered = sorted(abs(v) for v in vals)
        p95 = ordered[int(0.95 * (len(ordered) - 1))]
        med = median(vals)
        return {
            "venue": venue,
            "samples": len(vals),
            "median_offset_ms": med,
            "p95_offset_ms": p95,
            "stale": p95 > self.stale_ms,
        }

    def snapshot(self) -> dict:
        venues = [self.venue_stats(v) for v in sorted(self.by_venue)]
        return {
            "samples": len(self.samples),
            "stale_threshold_ms": self.stale_ms,
            "venues": venues,
            "any_stale": any(v["stale"] for v in venues),
        }
