"""Experiment planning helpers for the Strategy Factory path."""
from __future__ import annotations

from typing import Any
import uuid


def plan_experiment(
    hypothesis: str,
    strategy_id: str = "cross_venue_arbitrage",
    focus: str = "edge_stability",
) -> dict[str, Any]:
    focus = (focus or "edge_stability").lower()
    if focus in {"robustness", "monte_carlo", "mc"}:
        params = {"min_net_edge_bps": 8.0, "default_slippage_bps": 2.0}
        ticks, mc_runs = 2400, 40
        notes = ["Emphasize Monte Carlo p05 and ruin rate before promotion."]
    elif focus in {"sensitivity", "parameters"}:
        params = {"min_net_edge_bps": 8.0}
        ticks, mc_runs = 2000, 20
        notes = ["Sweep min_net_edge_bps across 4–20 bp and require sensitivity stability."]
    else:
        params = {"min_net_edge_bps": 8.0, "default_slippage_bps": 2.0}
        ticks, mc_runs = 2400, 30
        notes = ["Prioritize walk-forward OOS stability with cost-aware expectancy."]

    plan_id = f"plan_{uuid.uuid4().hex[:10]}"
    steps = [
        {"step": 1, "action": "register_experiment", "endpoint": "POST /api/v1/research/suite"},
        {"step": 2, "action": "walk_forward", "params": {"ticks": ticks, "train_size": 800, "test_size": 200, "step": 200}},
        {"step": 3, "action": "monte_carlo", "params": {"ticks": min(ticks, 1500), "runs": mc_runs}},
        {"step": 4, "action": "sensitivity", "params": {"parameter": "min_net_edge_bps", "values": [4, 6, 8, 10, 12, 16, 20]}},
        {"step": 5, "action": "promotion_gate", "endpoint": f"POST /api/v1/research/promote/{{experiment_id}}?stage=paper"},
        {"step": 6, "action": "shadow_observe", "note": "Never jump to live; shadow/testnet only after gates."},
    ]
    return {
        "kind": "experiment_plan",
        "plan_id": plan_id,
        "hypothesis": hypothesis,
        "strategy_id": strategy_id,
        "focus": focus,
        "suggested_params": params,
        "suite": {"ticks": ticks, "mc_runs": mc_runs, "stage": "paper"},
        "steps": steps,
        "notes": notes + [
            "PromotionGate remains deterministic and non-bypassable by copilot.",
            "Live capital and signing keys are out of scope for generated plans.",
        ],
        "advisory": True,
        "execution_authority": False,
    }
