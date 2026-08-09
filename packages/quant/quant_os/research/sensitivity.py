"""Parameter sensitivity / robustness surface for strategy knobs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from quant_os.backtest import ArbitrageBacktester, BacktestResult
from .datasets import QuoteDataset


@dataclass
class SensitivityPoint:
    params: dict[str, float]
    result: BacktestResult

    def to_dict(self) -> dict:
        return {"params": self.params, "result": self.result.to_dict()}


@dataclass
class SensitivityResult:
    parameter: str
    points: list[SensitivityPoint] = field(default_factory=list)
    best_params: dict[str, float] = field(default_factory=dict)
    best_net_pnl: float = 0.0
    pnl_range: float = 0.0
    stability_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "points": [p.to_dict() for p in self.points],
            "best_params": self.best_params,
            "best_net_pnl": self.best_net_pnl,
            "pnl_range": self.pnl_range,
            "stability_score": self.stability_score,
        }


@dataclass
class ParameterSensitivity:
    """
    Sweep one or more parameters.
    `strategy_factory(params)` returns a strategy configured with those params.
    """

    strategy_factory: Callable[[dict[str, float]], Any]
    notional: float = 1000

    def sweep(
        self,
        dataset: QuoteDataset,
        parameter: str,
        values: list[float],
        base_params: dict[str, float] | None = None,
    ) -> SensitivityResult:
        base = dict(base_params or {})
        points: list[SensitivityPoint] = []
        for value in values:
            params = {**base, parameter: float(value)}
            strategy = self.strategy_factory(params)
            result = ArbitrageBacktester(strategy, self.notional).run(dataset.batches)
            points.append(SensitivityPoint(params, result))

        if not points:
            raise ValueError("no sensitivity points produced")

        best = max(points, key=lambda p: p.result.net_pnl)
        pnls = [p.result.net_pnl for p in points]
        pnl_range = max(pnls) - min(pnls)
        # Stability: fraction of values with non-negative pnl and limited range vs best.
        nonneg = sum(1 for p in pnls if p >= 0) / len(pnls)
        scale = abs(best.result.net_pnl) if best.result.net_pnl else 1.0
        stability = max(0.0, min(1.0, nonneg * (1 - min(1.0, pnl_range / scale))))

        return SensitivityResult(
            parameter=parameter,
            points=points,
            best_params=best.params,
            best_net_pnl=best.result.net_pnl,
            pnl_range=round(pnl_range, 2),
            stability_score=round(stability, 4),
        )

    def grid(
        self,
        dataset: QuoteDataset,
        grid: dict[str, list[float]],
        base_params: dict[str, float] | None = None,
    ) -> list[SensitivityPoint]:
        """Cartesian product sweep for small grids."""
        base = dict(base_params or {})
        keys = list(grid)
        if not keys:
            return []
        points: list[SensitivityPoint] = []

        def rec(i: int, cur: dict[str, float]):
            if i == len(keys):
                strategy = self.strategy_factory(cur)
                result = ArbitrageBacktester(strategy, self.notional).run(dataset.batches)
                points.append(SensitivityPoint(dict(cur), result))
                return
            key = keys[i]
            for value in grid[key]:
                cur[key] = float(value)
                rec(i + 1, cur)
            cur.pop(key, None)

        rec(0, dict(base))
        return points
