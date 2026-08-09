"""AI Quant Copilot facade — research/control plane only."""
from __future__ import annotations

from typing import Any

from .analytics import answer_question
from .anomalies import analyze_anomalies
from .codegen import generate_strategy_stub
from .explain import explain_fill, explain_strategy
from .planning import plan_experiment
from .policies import CopilotGuardrails, PolicyDecision


class AICopilot:
    def __init__(self):
        self.guardrails = CopilotGuardrails()
        self._history: list[dict[str, Any]] = []

    def _guard(self, text: str) -> PolicyDecision | None:
        decision = self.guardrails.evaluate(text)
        if decision.allowed:
            return None
        return decision

    def explain_strategy(self, **kwargs) -> dict[str, Any]:
        blocked = self._guard(str(kwargs))
        if blocked:
            return {"ok": False, "policy": blocked.to_dict()}
        result = explain_strategy(**kwargs)
        self._remember("explain_strategy", result)
        return {"ok": True, **result}

    def explain_fill(self, fill: dict[str, Any]) -> dict[str, Any]:
        blocked = self._guard(str(fill))
        if blocked:
            return {"ok": False, "policy": blocked.to_dict()}
        result = explain_fill(fill)
        self._remember("explain_fill", result)
        return {"ok": True, **result}

    def plan_experiment(self, hypothesis: str, strategy_id: str = "cross_venue_arbitrage", focus: str = "edge_stability") -> dict[str, Any]:
        blocked = self._guard(hypothesis)
        if blocked:
            return {"ok": False, "policy": blocked.to_dict()}
        result = plan_experiment(hypothesis=hypothesis, strategy_id=strategy_id, focus=focus)
        self._remember("plan_experiment", result)
        return {"ok": True, **result}

    def analyze(self, **kwargs) -> dict[str, Any]:
        result = analyze_anomalies(**kwargs)
        self._remember("analyze", result)
        return {"ok": True, **result}

    def ask(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        blocked = self._guard(question)
        if blocked:
            return {
                "ok": False,
                "kind": "nl_analytics",
                "intent": "policy_refusal",
                "question": question,
                "answer": blocked.advice,
                "policy": blocked.to_dict(),
            }
        result = answer_question(question, context=context)
        self._remember("ask", result)
        return {"ok": True, **result}

    def codegen(
        self,
        name: str,
        kind: str = "cross_venue_arbitrage",
        hypothesis: str = "",
        min_net_edge_bps: float = 8.0,
    ) -> dict[str, Any]:
        result = generate_strategy_stub(
            name=name,
            kind=kind,
            hypothesis=hypothesis,
            min_net_edge_bps=min_net_edge_bps,
            guardrails=self.guardrails,
        )
        self._remember("codegen", {"ok": result.get("ok"), "stub_id": result.get("stub_id")})
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "provider": "deterministic_local",
            "plane": "research_control",
            "guardrails": self.guardrails.snapshot(),
            "history": len(self._history),
            "recent": self._history[-10:],
            "capabilities": [
                "strategy_explanations",
                "experiment_planning",
                "anomaly_analysis",
                "nl_analytics",
                "governed_codegen",
            ],
        }

    def _remember(self, action: str, payload: dict[str, Any]) -> None:
        self._history.append({
            "action": action,
            "kind": payload.get("kind"),
            "summary": payload.get("summary") or payload.get("answer") or payload.get("plan_id") or payload.get("stub_id"),
        })
        if len(self._history) > 200:
            self._history = self._history[-200:]
