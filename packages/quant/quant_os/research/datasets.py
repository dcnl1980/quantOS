"""Synthetic and replayable quote datasets for research."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from quant_os.models import Quote


@dataclass
class QuoteDataset:
    name: str
    symbol: str
    batches: list[list[Quote]]
    seed: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.batches)

    def slice(self, start: int, end: int) -> "QuoteDataset":
        return QuoteDataset(
            name=f"{self.name}[{start}:{end}]",
            symbol=self.symbol,
            batches=self.batches[start:end],
            seed=self.seed,
            metadata={**self.metadata, "slice": [start, end]},
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "size": self.size,
            "seed": self.seed,
            "metadata": self.metadata,
        }


def synthesize_arbitrage_batches(
    ticks: int = 2000,
    symbol: str = "BTCUSDT",
    seed: int = 7,
    base_price: float = 118000.0,
    arb_probability: float = 0.06,
    arb_dislocation_bps: tuple[float, float] = (14.0, 42.0),
    venues: tuple[str, str] = ("sim_a", "sim_b"),
) -> QuoteDataset:
    rng = random.Random(seed)
    base = base_price
    batches: list[list[Quote]] = []
    for i in range(max(1, ticks)):
        base *= math.exp(rng.gauss(0, 0.00012))
        if rng.random() < arb_probability:
            dis = rng.uniform(*arb_dislocation_bps)
        else:
            dis = rng.uniform(-1.5, 1.5)
        now = datetime.now(timezone.utc) + timedelta(milliseconds=i * 100)

        def q(venue: str, offset_bps: float) -> Quote:
            mid = base * (1 + offset_bps / 10000)
            return Quote(
                venue, symbol, mid * 0.99995, mid * 1.00005,
                2.0, 2.0, now, now, i,
            )

        batches.append([q(venues[0], 0.0), q(venues[1], dis)])
    return QuoteDataset(
        name=f"synth_{symbol.lower()}_{ticks}",
        symbol=symbol,
        batches=batches,
        seed=seed,
        metadata={
            "arb_probability": arb_probability,
            "arb_dislocation_bps": list(arb_dislocation_bps),
            "venues": list(venues),
            "base_price": base_price,
        },
    )
