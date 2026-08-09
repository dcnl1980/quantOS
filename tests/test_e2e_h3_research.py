"""End-to-end H3 research suite through ResearchLab and FastAPI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "quant"))
sys.path.insert(0, str(ROOT / "services" / "api"))

os.environ.setdefault("EXECUTION_ENGINE", "python")
os.environ.setdefault("MARKET_MODE", "simulator")
os.environ.setdefault("EXECUTION_MODE", "paper")
os.environ.setdefault("ENABLE_L2_BOOKS", "false")
os.environ.setdefault("DATA_PLANE_ENABLED", "true")
os.environ.setdefault("BUS_BACKEND", "memory")
os.environ.setdefault("ARCHIVE_BACKEND", "memory")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("PAPER_AUTO_EXECUTE", "false")
os.environ.setdefault("SIM_TICK_MS", "250")

from app.research.lab import ResearchLab  # noqa: E402
from quant_os.research import PromotionGate  # noqa: E402


def _soft_gate() -> PromotionGate:
    return PromotionGate(
        min_trades=5,
        min_expectancy=-1.0,
        max_drawdown_pct=100.0,
        min_oos_stability=0.0,
        min_mc_robustness=0.0,
        min_mc_p05_pnl=-1e9,
        min_sensitivity_stability=0.0,
        min_win_rate=0.0,
        require_positive_oos=True,
    )


def test_e2e_research_full_suite_and_promote():
    lab = ResearchLab(
        fees={"sim_a": 5, "sim_b": 5},
        default_slippage_bps=2,
        min_net_edge_bps=6,
        notional=1000,
        gate=_soft_gate(),
    )
    suite = lab.run_full_suite(ticks=1600, seed=11, mc_runs=10, stage="paper")
    assert suite["experiment_id"]
    assert "walk_forward" in suite
    assert "monte_carlo" in suite
    assert "sensitivity" in suite
    assert suite["features"]["computed"] > 0
    exp = lab.experiments.get(suite["experiment_id"])
    assert exp is not None
    assert exp.metrics.get("oos_net_pnl") is not None

    promoted = lab.promote(suite["experiment_id"], stage="paper")
    assert "promotion" in promoted
    snap = lab.snapshot()
    assert snap["experiments"]["count"] >= 1
    assert "cross_venue_arbitrage" in snap["governance"]["statuses"]


def test_e2e_research_api_endpoints():
    from fastapi.testclient import TestClient
    from app.config import settings
    from app.main import app
    from app.runtime import runtime

    settings.paper_auto_execute = False
    settings.enable_l2_books = False
    settings.otel_enabled = False
    runtime.research.governor.gate = _soft_gate()

    with TestClient(app) as client:
        wf = client.post(
            "/api/v1/research/walk-forward?ticks=1400&seed=3&train_size=600&test_size=200&step=200"
        )
        assert wf.status_code == 200
        body = wf.json()
        assert body["walk_forward"]["fold_count"] >= 1

        mc = client.post("/api/v1/research/monte-carlo?ticks=800&seed=3&runs=8")
        assert mc.status_code == 200
        assert mc.json()["monte_carlo"]["runs"] == 8

        sens = client.post("/api/v1/research/sensitivity?ticks=600&seed=3&values=6,8,12")
        assert sens.status_code == 200
        assert len(sens.json()["sensitivity"]["points"]) == 3

        suite = client.post("/api/v1/research/suite?ticks=1400&seed=3&mc_runs=8")
        assert suite.status_code == 200
        suite_body = suite.json()
        exp_id = suite_body["experiment_id"]
        assert exp_id

        experiments = client.get("/api/v1/research/experiments").json()
        assert any(e["id"] == exp_id for e in experiments)

        one = client.get(f"/api/v1/research/experiments/{exp_id}").json()
        assert one["id"] == exp_id

        promo = client.post(f"/api/v1/research/promote/{exp_id}?stage=paper").json()
        assert "promotion" in promo

        features = client.get("/api/v1/research/features").json()
        assert "computed" in features

        gov = client.get("/api/v1/research/governance").json()
        assert "gate" in gov

        plane = client.get("/api/v1/research").json()
        assert "experiments" in plane

        snap = client.get("/api/v1/snapshot").json()
        assert "research" in snap
