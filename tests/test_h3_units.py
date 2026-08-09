from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.research import (
    synthesize_arbitrage_batches,
    FeatureStore,
    WalkForwardValidator,
    MonteCarloRunner,
    ParameterSensitivity,
    ExperimentRegistry,
    ExperimentStatus,
    PromotionGate,
    StrategyGovernor,
)


def _strategy(min_edge=8.0):
    return CrossVenueArbitrage(CostModel({"sim_a": 5, "sim_b": 5}, 2), min_edge)


def test_synthesize_dataset_and_features():
    ds = synthesize_arbitrage_batches(ticks=100, seed=1, arb_probability=0.2)
    assert ds.size == 100
    store = FeatureStore()
    n = store.ingest_dataset(ds.batches)
    assert n == 100
    snap = store.snapshot()
    assert snap["computed"] >= 100
    assert any(f["name"] == "cross_venue_gross_bps" for f in snap["features"])


def test_walk_forward_oos_metrics():
    ds = synthesize_arbitrage_batches(ticks=1400, seed=3, arb_probability=0.12)
    wf = WalkForwardValidator(
        strategy_factory=lambda _i: _strategy(8),
        notional=1000,
        train_size=600,
        test_size=200,
        step=200,
    ).run(ds)
    assert wf.folds
    assert "oos_net_pnl" in wf.to_dict()
    assert 0 <= wf.stability_score <= 1


def test_monte_carlo_perturbation():
    ds = synthesize_arbitrage_batches(ticks=800, seed=5, arb_probability=0.15)
    mc = MonteCarloRunner(
        strategy_factory=lambda: _strategy(8),
        notional=1000,
        runs=12,
        seed=9,
    ).run(ds)
    assert mc.runs == 12
    assert "p05_net_pnl" in mc.to_dict()
    assert 0 <= mc.robustness_score <= 1


def test_parameter_sensitivity_sweep():
    ds = synthesize_arbitrage_batches(ticks=600, seed=2, arb_probability=0.2)
    sens = ParameterSensitivity(
        strategy_factory=lambda p: _strategy(p.get("min_net_edge_bps", 8)),
        notional=1000,
    ).sweep(ds, "min_net_edge_bps", [4, 8, 16])
    assert len(sens.points) == 3
    assert "min_net_edge_bps" in sens.best_params


def test_experiment_registry_lifecycle():
    reg = ExperimentRegistry()
    exp = reg.create("t1", "cross_venue_arbitrage", "edge persists OOS", {"min_net_edge_bps": 8})
    reg.update_status(exp.id, ExperimentStatus.RUNNING)
    reg.complete(exp.id, {"oos_net_pnl": 12.0}, {"note": "ok"})
    assert reg.get(exp.id).status == ExperimentStatus.COMPLETED
    assert reg.snapshot()["count"] == 1


def test_promotion_gate_pass_and_fail():
    gate = PromotionGate(
        min_trades=10,
        min_expectancy=0.0,
        max_drawdown_pct=20.0,
        min_oos_stability=0.2,
        min_mc_robustness=0.2,
        min_mc_p05_pnl=-10.0,
        min_sensitivity_stability=0.1,
        min_win_rate=10.0,
    )
    good = gate.evaluate({
        "traded": 50,
        "expectancy": 1.5,
        "max_drawdown_pct": 2.0,
        "win_rate": 60,
        "stability_score": 0.8,
        "robustness_score": 0.7,
        "p05_net_pnl": 5.0,
        "sensitivity_stability": 0.6,
        "oos_net_pnl": 20.0,
    })
    assert good.approved is True

    bad = gate.evaluate({
        "traded": 2,
        "expectancy": -1.0,
        "max_drawdown_pct": 50.0,
        "win_rate": 5,
        "stability_score": 0.0,
        "robustness_score": 0.0,
        "p05_net_pnl": -100.0,
        "sensitivity_stability": 0.0,
        "oos_net_pnl": -20.0,
    })
    assert bad.approved is False
    gov = StrategyGovernor(gate=gate)
    d = gov.evaluate_promotion("cross_venue_arbitrage", {
        "traded": 50,
        "expectancy": 1.5,
        "max_drawdown_pct": 2.0,
        "win_rate": 60,
        "stability_score": 0.8,
        "robustness_score": 0.7,
        "p05_net_pnl": 5.0,
        "sensitivity_stability": 0.6,
        "oos_net_pnl": 20.0,
    }, stage="paper")
    assert d.approved is True
    assert gov.statuses["cross_venue_arbitrage"].startswith("promoted")
