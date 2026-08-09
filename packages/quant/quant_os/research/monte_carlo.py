"""Monte Carlo perturbation of quote paths for robustness checks."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable

from quant_os.backtest import ArbitrageBacktester, BacktestResult
from quant_os.models import Quote
from .datasets import QuoteDataset


@dataclass
class MonteCarloResult:
    runs: int
    base: BacktestResult
    samples: list[BacktestResult] = field(default_factory=list)
    mean_net_pnl: float = 0.0
    p05_net_pnl: float = 0.0
    p50_net_pnl: float = 0.0
    p95_net_pnl: float = 0.0
    mean_max_drawdown_pct: float = 0.0
    ruin_rate: float = 0.0  # fraction of runs with net_pnl < 0
    robustness_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "base": self.base.to_dict(),
            "mean_net_pnl": self.mean_net_pnl,
            "p05_net_pnl": self.p05_net_pnl,
            "p50_net_pnl": self.p50_net_pnl,
            "p95_net_pnl": self.p95_net_pnl,
            "mean_max_drawdown_pct": self.mean_max_drawdown_pct,
            "ruin_rate": self.ruin_rate,
            "robustness_score": self.robustness_score,
            "sample_count": len(self.samples),
            "samples": [s.to_dict() for s in self.samples[:20]],
        }


@dataclass
class MonteCarloRunner:
    strategy_factory: Callable[[], Any]
    notional: float = 1000
    runs: int = 50
    seed: int = 11
    price_noise_bps: float = 3.0
    dislocation_noise_bps: float = 5.0
    drop_prob: float = 0.02

    def run(self, dataset: QuoteDataset) -> MonteCarloResult:
        base_strategy = self.strategy_factory()
        base = ArbitrageBacktester(base_strategy, self.notional).run(dataset.batches)
        rng = random.Random(self.seed)
        samples: list[BacktestResult] = []
        for i in range(max(1, self.runs)):
            perturbed = self._perturb(dataset.batches, random.Random(rng.randint(1, 1_000_000_000)))
            strategy = self.strategy_factory()
            samples.append(ArbitrageBacktester(strategy, self.notional).run(perturbed))

        pnls = sorted(s.net_pnl for s in samples)
        dds = [s.max_drawdown_pct for s in samples]
        mean_pnl = sum(pnls) / len(pnls)
        ruin = sum(1 for p in pnls if p < 0) / len(pnls)
        # Robustness: high if p05>0 and ruin low and mean close to base.
        p05 = _percentile(pnls, 0.05)
        score = 0.0
        if p05 > 0:
            score += 0.5
        score += 0.3 * (1 - ruin)
        if base.net_pnl != 0:
            score += 0.2 * max(0.0, 1 - abs(mean_pnl - base.net_pnl) / abs(base.net_pnl))
        else:
            score += 0.2 if abs(mean_pnl) < 1e-9 else 0.0

        return MonteCarloResult(
            runs=len(samples),
            base=base,
            samples=samples,
            mean_net_pnl=round(mean_pnl, 2),
            p05_net_pnl=round(p05, 2),
            p50_net_pnl=round(_percentile(pnls, 0.50), 2),
            p95_net_pnl=round(_percentile(pnls, 0.95), 2),
            mean_max_drawdown_pct=round(sum(dds) / len(dds), 4),
            ruin_rate=round(ruin, 4),
            robustness_score=round(min(1.0, score), 4),
        )

    def _perturb(self, batches: list[list[Quote]], rng: random.Random) -> list[list[Quote]]:
        out: list[list[Quote]] = []
        for quotes in batches:
            if rng.random() < self.drop_prob:
                continue
            row: list[Quote] = []
            # Shared dislocation shock so arb edges are stressed, not erased randomly.
            shock = rng.gauss(0, self.dislocation_noise_bps)
            for q in quotes:
                noise = rng.gauss(0, self.price_noise_bps) + (
                    shock if q.venue.endswith("b") or q.venue == quotes[-1].venue else 0.0
                )
                scale = 1 + noise / 10000
                row.append(Quote(
                    q.venue, q.symbol,
                    max(1e-9, q.bid * scale),
                    max(1e-9, q.ask * scale),
                    q.bid_size, q.ask_size,
                    q.exchange_ts, q.received_ts, q.sequence,
                ))
            if row:
                out.append(row)
        return out or batches


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = p * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    w = idx - lo
    return sorted_vals[lo] * (1 - w) + sorted_vals[hi] * w
