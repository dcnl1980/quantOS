"""Walk-forward validation over sequential train/test folds."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from quant_os.backtest import ArbitrageBacktester, BacktestResult
from .datasets import QuoteDataset


@dataclass
class FoldResult:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train: BacktestResult
    test: BacktestResult

    def to_dict(self) -> dict:
        return {
            "fold": self.fold,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train": self.train.to_dict(),
            "test": self.test.to_dict(),
            "oos_net_pnl": self.test.net_pnl,
            "oos_win_rate": self.test.win_rate,
            "oos_max_drawdown_pct": self.test.max_drawdown_pct,
        }


@dataclass
class WalkForwardResult:
    folds: list[FoldResult] = field(default_factory=list)
    oos_net_pnl: float = 0.0
    oos_win_rate: float = 0.0
    oos_max_drawdown_pct: float = 0.0
    stability_score: float = 0.0
    positive_folds: int = 0

    def to_dict(self) -> dict:
        return {
            "folds": [f.to_dict() for f in self.folds],
            "fold_count": len(self.folds),
            "oos_net_pnl": self.oos_net_pnl,
            "oos_win_rate": self.oos_win_rate,
            "oos_max_drawdown_pct": self.oos_max_drawdown_pct,
            "stability_score": self.stability_score,
            "positive_folds": self.positive_folds,
        }


@dataclass
class WalkForwardValidator:
    """
    Rolling walk-forward:
      [train_size] -> [test_size] slide by step.
    `strategy_factory(fold_index)` builds a fresh strategy for each fold.
    """

    strategy_factory: Callable[[int], Any]
    notional: float = 1000
    train_size: int = 800
    test_size: int = 200
    step: int = 200

    def run(self, dataset: QuoteDataset) -> WalkForwardResult:
        n = dataset.size
        if n < self.train_size + self.test_size:
            raise ValueError(
                f"dataset size {n} < train({self.train_size})+test({self.test_size})"
            )
        folds: list[FoldResult] = []
        start = 0
        fold_i = 0
        while start + self.train_size + self.test_size <= n:
            train_start = start
            train_end = start + self.train_size
            test_start = train_end
            test_end = train_end + self.test_size
            strategy = self.strategy_factory(fold_i)
            bt = ArbitrageBacktester(strategy, self.notional)
            train = bt.run(dataset.batches[train_start:train_end])
            test = bt.run(dataset.batches[test_start:test_end])
            folds.append(FoldResult(
                fold_i, train_start, train_end, test_start, test_end, train, test,
            ))
            fold_i += 1
            start += self.step

        if not folds:
            raise ValueError("no walk-forward folds produced")

        oos_pnl = sum(f.test.net_pnl for f in folds)
        traded = sum(f.test.traded for f in folds)
        wins = sum(f.test.win_rate * f.test.traded / 100 for f in folds)
        oos_wr = (wins / traded * 100) if traded else 0.0
        oos_dd = max(f.test.max_drawdown_pct for f in folds)
        positive = sum(1 for f in folds if f.test.net_pnl > 0)
        # Stability: fraction of positive OOS folds * (1 - relative pnl dispersion).
        pnls = [f.test.net_pnl for f in folds]
        avg = sum(pnls) / len(pnls)
        dispersion = (sum(abs(p - avg) for p in pnls) / len(pnls) / abs(avg)) if avg else 1.0
        stability = max(0.0, min(1.0, (positive / len(folds)) * (1 - min(1.0, dispersion))))

        return WalkForwardResult(
            folds=folds,
            oos_net_pnl=round(oos_pnl, 2),
            oos_win_rate=round(oos_wr, 2),
            oos_max_drawdown_pct=round(oos_dd, 4),
            stability_score=round(stability, 4),
            positive_folds=positive,
        )
