"""H3 research lab: walk-forward, Monte Carlo, sensitivity, experiments, promotion."""
from __future__ import annotations

from typing import Any

from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.backtest import ArbitrageBacktester
from quant_os.research import (
    FeatureStore,
    ExperimentRegistry,
    ExperimentStatus,
    WalkForwardValidator,
    MonteCarloRunner,
    ParameterSensitivity,
    StrategyGovernor,
    PromotionGate,
    synthesize_arbitrage_batches,
)


class ResearchLab:
    def __init__(
        self,
        fees: dict[str, float],
        default_slippage_bps: float = 2.0,
        min_net_edge_bps: float = 8.0,
        notional: float = 1000.0,
        gate: PromotionGate | None = None,
    ):
        self.fees = fees
        self.default_slippage_bps = default_slippage_bps
        self.min_net_edge_bps = min_net_edge_bps
        self.notional = notional
        self.features = FeatureStore()
        self.experiments = ExperimentRegistry()
        self.governor = StrategyGovernor(gate=gate or PromotionGate())

    def _strategy(self, params: dict[str, float] | None = None) -> CrossVenueArbitrage:
        params = params or {}
        min_edge = float(params.get("min_net_edge_bps", self.min_net_edge_bps))
        slip = float(params.get("default_slippage_bps", self.default_slippage_bps))
        fee_scale = float(params.get("fee_scale", 1.0))
        fees = {k: v * fee_scale for k, v in self.fees.items()}
        return CrossVenueArbitrage(CostModel(fees, slip), min_edge)

    def make_dataset(
        self,
        ticks: int = 2000,
        seed: int = 7,
        symbol: str = "BTCUSDT",
        arb_probability: float = 0.06,
    ):
        return synthesize_arbitrage_batches(
            ticks=ticks,
            seed=seed,
            symbol=symbol,
            arb_probability=arb_probability,
        )

    def run_baseline(self, ticks: int = 2000, seed: int = 7, params: dict | None = None) -> dict:
        dataset = self.make_dataset(ticks=ticks, seed=seed)
        self.features.ingest_dataset(dataset.batches, max_batches=min(500, dataset.size))
        result = ArbitrageBacktester(self._strategy(params), self.notional).run(dataset.batches)
        return {"dataset": dataset.to_dict(), "result": result.to_dict()}

    def run_walk_forward(
        self,
        ticks: int = 2400,
        seed: int = 7,
        train_size: int = 800,
        test_size: int = 200,
        step: int = 200,
        params: dict | None = None,
        register: bool = True,
    ) -> dict:
        dataset = self.make_dataset(ticks=ticks, seed=seed)
        self.features.ingest_dataset(dataset.batches, max_batches=min(500, dataset.size))
        base_params = dict(params or {})
        validator = WalkForwardValidator(
            strategy_factory=lambda _fold: self._strategy(base_params),
            notional=self.notional,
            train_size=train_size,
            test_size=test_size,
            step=step,
        )
        wf = validator.run(dataset)
        metrics = {
            "oos_net_pnl": wf.oos_net_pnl,
            "oos_win_rate": wf.oos_win_rate,
            "oos_max_drawdown_pct": wf.oos_max_drawdown_pct,
            "stability_score": wf.stability_score,
            "traded": sum(f.test.traded for f in wf.folds),
            "expectancy": (
                wf.oos_net_pnl / sum(f.test.traded for f in wf.folds)
                if sum(f.test.traded for f in wf.folds) else 0.0
            ),
        }
        exp = None
        if register:
            exp = self.experiments.create(
                name=f"walk_forward_{dataset.name}",
                strategy_id="cross_venue_arbitrage",
                hypothesis="OOS walk-forward remains profitable after costs",
                params=base_params,
                dataset=dataset.to_dict(),
            )
            self.experiments.complete(exp.id, metrics, {"walk_forward": wf.to_dict()})
        return {
            "dataset": dataset.to_dict(),
            "walk_forward": wf.to_dict(),
            "metrics": metrics,
            "experiment_id": exp.id if exp else None,
        }

    def run_monte_carlo(
        self,
        ticks: int = 1500,
        seed: int = 7,
        runs: int = 40,
        params: dict | None = None,
        register: bool = True,
    ) -> dict:
        dataset = self.make_dataset(ticks=ticks, seed=seed)
        base_params = dict(params or {})
        runner = MonteCarloRunner(
            strategy_factory=lambda: self._strategy(base_params),
            notional=self.notional,
            runs=runs,
            seed=seed + 99,
        )
        mc = runner.run(dataset)
        metrics = {
            "net_pnl": mc.base.net_pnl,
            "traded": mc.base.traded,
            "expectancy": mc.base.expectancy,
            "max_drawdown_pct": mc.mean_max_drawdown_pct,
            "win_rate": mc.base.win_rate,
            "robustness_score": mc.robustness_score,
            "p05_net_pnl": mc.p05_net_pnl,
            "ruin_rate": mc.ruin_rate,
        }
        exp = None
        if register:
            exp = self.experiments.create(
                name=f"monte_carlo_{dataset.name}",
                strategy_id="cross_venue_arbitrage",
                hypothesis="Edge survives quote path perturbations",
                params=base_params,
                dataset=dataset.to_dict(),
            )
            self.experiments.complete(exp.id, metrics, {"monte_carlo": mc.to_dict()})
        return {
            "dataset": dataset.to_dict(),
            "monte_carlo": mc.to_dict(),
            "metrics": metrics,
            "experiment_id": exp.id if exp else None,
        }

    def run_sensitivity(
        self,
        ticks: int = 1500,
        seed: int = 7,
        parameter: str = "min_net_edge_bps",
        values: list[float] | None = None,
        base_params: dict | None = None,
        register: bool = True,
    ) -> dict:
        dataset = self.make_dataset(ticks=ticks, seed=seed)
        values = values or [4, 6, 8, 10, 12, 16, 20]
        sweep = ParameterSensitivity(
            strategy_factory=lambda p: self._strategy(p),
            notional=self.notional,
        )
        result = sweep.sweep(dataset, parameter, values, base_params=base_params)
        metrics = {
            "sensitivity_stability": result.stability_score,
            "best_net_pnl": result.best_net_pnl,
            "pnl_range": result.pnl_range,
            "best_params": result.best_params,
        }
        exp = None
        if register:
            exp = self.experiments.create(
                name=f"sensitivity_{parameter}_{dataset.name}",
                strategy_id="cross_venue_arbitrage",
                hypothesis=f"Parameter {parameter} is robust near current settings",
                params=dict(base_params or {}),
                dataset=dataset.to_dict(),
            )
            self.experiments.complete(exp.id, metrics, {"sensitivity": result.to_dict()})
        return {
            "dataset": dataset.to_dict(),
            "sensitivity": result.to_dict(),
            "metrics": metrics,
            "experiment_id": exp.id if exp else None,
        }

    def run_full_suite(
        self,
        ticks: int = 2400,
        seed: int = 7,
        mc_runs: int = 30,
        params: dict | None = None,
        stage: str = "paper",
    ) -> dict:
        params = dict(params or {})
        exp = self.experiments.create(
            name=f"full_suite_seed{seed}",
            strategy_id="cross_venue_arbitrage",
            hypothesis="Candidate passes walk-forward, Monte Carlo and sensitivity gates",
            params=params,
        )
        self.experiments.update_status(exp.id, ExperimentStatus.RUNNING)

        try:
            wf = self.run_walk_forward(ticks=ticks, seed=seed, params=params, register=False)
            mc = self.run_monte_carlo(
                ticks=min(ticks, 1500), seed=seed, runs=mc_runs, params=params, register=False
            )
            sens = self.run_sensitivity(
                ticks=min(ticks, 1500), seed=seed, base_params=params, register=False
            )
            metrics = {
                **wf["metrics"],
                **mc["metrics"],
                "sensitivity_stability": sens["metrics"]["sensitivity_stability"],
                "best_params": sens["metrics"]["best_params"],
            }
            decision = self.governor.evaluate_promotion(
                "cross_venue_arbitrage", metrics, stage=stage, experiment_id=exp.id
            )
            artifacts = {
                "walk_forward": wf["walk_forward"],
                "monte_carlo": mc["monte_carlo"],
                "sensitivity": sens["sensitivity"],
                "promotion": decision.to_dict(),
            }
            self.experiments.complete(exp.id, metrics, artifacts)
            if decision.approved:
                self.experiments.update_status(exp.id, ExperimentStatus.PROMOTED, "promotion_gates_passed")
            else:
                self.experiments.update_status(exp.id, ExperimentStatus.REJECTED, ";".join(decision.reasons))
            return {
                "experiment_id": exp.id,
                "metrics": metrics,
                "promotion": decision.to_dict(),
                "walk_forward": wf["walk_forward"],
                "monte_carlo": mc["monte_carlo"],
                "sensitivity": sens["sensitivity"],
                "features": self.features.snapshot(),
            }
        except Exception as exc:
            self.experiments.fail(exp.id, str(exc))
            raise

    def promote(self, experiment_id: str, stage: str = "paper") -> dict:
        exp = self.experiments.get(experiment_id)
        if not exp:
            return {"ok": False, "reason": "unknown_experiment"}
        decision = self.governor.evaluate_promotion(
            exp.strategy_id, exp.metrics, stage=stage, experiment_id=exp.id
        )
        if decision.approved:
            self.experiments.update_status(exp.id, ExperimentStatus.PROMOTED, f"promoted_to_{stage}")
        else:
            self.experiments.update_status(exp.id, ExperimentStatus.REJECTED, ";".join(decision.reasons))
        return {"ok": decision.approved, "experiment": exp.to_dict(), "promotion": decision.to_dict()}

    def snapshot(self) -> dict[str, Any]:
        return {
            "experiments": self.experiments.snapshot(),
            "features": self.features.snapshot(),
            "governance": self.governor.snapshot(),
            "defaults": {
                "min_net_edge_bps": self.min_net_edge_bps,
                "notional": self.notional,
                "default_slippage_bps": self.default_slippage_bps,
            },
        }
