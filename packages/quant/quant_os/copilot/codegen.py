"""Governed strategy stub generation — research plane only."""
from __future__ import annotations

from typing import Any
import re
import uuid

from .policies import CopilotGuardrails


ALLOWED_STRATEGY_KINDS = {
    "cross_venue_arbitrage",
    "lead_lag",
    "mean_reversion_research",
}


def generate_strategy_stub(
    name: str,
    kind: str = "cross_venue_arbitrage",
    hypothesis: str = "",
    min_net_edge_bps: float = 8.0,
    guardrails: CopilotGuardrails | None = None,
) -> dict[str, Any]:
    guardrails = guardrails or CopilotGuardrails()
    policy = guardrails.evaluate(f"{name} {kind} {hypothesis}")
    if not policy.allowed:
        return {
            "ok": False,
            "policy": policy.to_dict(),
            "code": None,
            "advisory": True,
            "execution_authority": False,
        }

    kind_norm = _normalize_kind(kind)
    if kind_norm not in ALLOWED_STRATEGY_KINDS:
        return {
            "ok": False,
            "policy": {
                "allowed": False,
                "reason": "unsupported_strategy_kind",
                "category": "unsupported_kind",
                "advice": f"Allowed kinds: {sorted(ALLOWED_STRATEGY_KINDS)}",
            },
            "code": None,
            "advisory": True,
            "execution_authority": False,
        }

    class_name = _to_class_name(name) or "ResearchStrategyCandidate"
    stub_id = f"stub_{uuid.uuid4().hex[:10]}"
    code = f'''"""Auto-generated research stub ({stub_id}).

GOVERNANCE:
- Research/control plane only.
- Must submit OrderRequests through RiskEngine / native risk gate.
- Must NOT import venue signing modules or set ENABLE_LIVE_TRADING.
- Promotion requires Strategy Factory gates (walk-forward, Monte Carlo, sensitivity).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quant_os.models import Quote, Opportunity


@dataclass(slots=True)
class {class_name}Config:
    min_net_edge_bps: float = {float(min_net_edge_bps)}
    hypothesis: str = {hypothesis!r}


class {class_name}:
    name = {name!r}
    strategy_id = {kind_norm!r}

    def __init__(self, config: {class_name}Config | None = None):
        self.config = config or {class_name}Config()

    def on_quotes(self, quotes: Iterable[Quote]) -> list[Opportunity]:
        """Candidate signal hook — wire into existing detectors/backtests only."""
        _ = quotes
        # Intentionally empty: use ResearchLab / existing detectors rather than
        # inventing an ungated execution path.
        return []
'''
    return {
        "ok": True,
        "stub_id": stub_id,
        "name": name,
        "kind": kind_norm,
        "hypothesis": hypothesis,
        "language": "python",
        "code": code,
        "constraints": [
            "no_risk_bypass",
            "no_signing_keys",
            "no_live_enablement",
            "requires_promotion_gate",
        ],
        "next_steps": [
            "Register an experiment via POST /api/v1/research/suite",
            "Promote only when PromotionGate approves",
            "Observe in paper/shadow before any testnet scale-up",
        ],
        "policy": policy.to_dict(),
        "advisory": True,
        "execution_authority": False,
    }


def _normalize_kind(kind: str) -> str:
    k = (kind or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "arbitrage": "cross_venue_arbitrage",
        "cross_venue": "cross_venue_arbitrage",
        "arb": "cross_venue_arbitrage",
        "leadlag": "lead_lag",
        "mean_reversion": "mean_reversion_research",
    }
    return aliases.get(k, k)


def _to_class_name(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name or "")
    if not parts:
        return "ResearchStrategyCandidate"
    return "".join(p[:1].upper() + p[1:] for p in parts)
