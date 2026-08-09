from __future__ import annotations

from dataclasses import dataclass, asdict, field


@dataclass(slots=True)
class BacktestResult:
    ticks: int
    opportunities: int
    traded: int
    gross_pnl: float
    estimated_costs: float
    net_pnl: float
    win_rate: float
    max_drawdown_pct: float = 0.0
    expectancy: float = 0.0
    avg_net_edge_bps: float = 0.0
    equity_curve: list[float] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        # Keep payload light for API lists; full curve available when short.
        if len(self.equity_curve) > 200:
            d["equity_curve"] = self.equity_curve[:: max(1, len(self.equity_curve) // 200)]
        return d


class ArbitrageBacktester:
    def __init__(self, strategy, notional: float = 1000):
        self.strategy = strategy
        self.notional = notional

    def run(self, batches) -> BacktestResult:
        ticks = ops = traded = wins = 0
        gross = costs = 0.0
        edge_sum = 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        curve: list[float] = []

        for quotes in batches:
            ticks += 1
            found = self.strategy.scan(quotes)
            ops += len(found)
            if not found:
                curve.append(equity)
                continue
            o = found[0]
            n = min(self.notional, o.max_notional or self.notional)
            g = n * o.gross_edge_bps / 10000
            net = n * o.net_edge_bps / 10000
            traded += 1
            gross += g
            costs += g - net
            wins += int(net > 0)
            edge_sum += o.net_edge_bps
            equity += net
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100)
            curve.append(equity)

        expectancy = (gross - costs) / traded if traded else 0.0
        return BacktestResult(
            ticks=ticks,
            opportunities=ops,
            traded=traded,
            gross_pnl=round(gross, 2),
            estimated_costs=round(costs, 2),
            net_pnl=round(gross - costs, 2),
            win_rate=round(wins / traded * 100 if traded else 0, 2),
            max_drawdown_pct=round(max_dd, 4),
            expectancy=round(expectancy, 4),
            avg_net_edge_bps=round(edge_sum / traded if traded else 0.0, 4),
            equity_curve=curve,
        )
