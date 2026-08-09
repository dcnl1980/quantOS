"""Venue fee-tier model (maker/taker by 30d volume)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FeeTier:
    name: str
    min_30d_volume: float
    maker_bps: float
    taker_bps: float


@dataclass
class FeeSchedule:
    venue_tiers: dict[str, list[FeeTier]] = field(default_factory=dict)
    volume_30d: dict[str, float] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "FeeSchedule":
        return cls(
            venue_tiers={
                "binance": [
                    FeeTier("vip0", 0, 10.0, 10.0),
                    FeeTier("vip1", 1_000_000, 9.0, 10.0),
                    FeeTier("vip2", 5_000_000, 8.0, 9.0),
                    FeeTier("vip3", 20_000_000, 6.0, 8.0),
                ],
                "coinbase": [
                    FeeTier("default", 0, 40.0, 60.0),
                    FeeTier("advanced", 100_000, 25.0, 40.0),
                    FeeTier("pro", 1_000_000, 15.0, 25.0),
                ],
                "sim_a": [FeeTier("sim", 0, 5.0, 5.0)],
                "sim_b": [FeeTier("sim", 0, 5.0, 5.0)],
                "binance_testnet": [FeeTier("testnet", 0, 10.0, 10.0)],
                "coinbase_testnet": [FeeTier("testnet", 0, 12.0, 12.0)],
            }
        )

    def set_volume(self, venue: str, volume: float):
        self.volume_30d[venue] = max(0.0, volume)

    def record_notional(self, venue: str, notional: float):
        self.volume_30d[venue] = self.volume_30d.get(venue, 0.0) + abs(notional)

    def tier_for(self, venue: str) -> FeeTier:
        tiers = self.venue_tiers.get(venue) or [FeeTier("default", 0, 10.0, 10.0)]
        vol = self.volume_30d.get(venue, 0.0)
        chosen = tiers[0]
        for tier in tiers:
            if vol >= tier.min_30d_volume:
                chosen = tier
        return chosen

    def taker_bps(self, venue: str) -> float:
        return self.tier_for(venue).taker_bps

    def maker_bps(self, venue: str) -> float:
        return self.tier_for(venue).maker_bps

    def as_fee_map(self, venues: list[str] | None = None) -> dict[str, float]:
        venues = venues or list(self.venue_tiers)
        return {v: self.taker_bps(v) for v in venues}

    def to_dict(self) -> dict:
        return {
            "volume_30d": dict(self.volume_30d),
            "tiers": {
                venue: {
                    "active": self.tier_for(venue).name,
                    "maker_bps": self.maker_bps(venue),
                    "taker_bps": self.taker_bps(venue),
                }
                for venue in self.venue_tiers
            },
        }
