"""Natural-language analytics router (deterministic intent matching)."""
from __future__ import annotations

from typing import Any
import re

from .anomalies import analyze_anomalies
from .explain import explain_strategy
from .planning import plan_experiment


def answer_question(
    question: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    q = (question or "").strip()
    lowered = q.lower()

    if re.search(r"\b(plan|design)\b.*\bexperiment\b|\bexperiment\b.*\bplan\b", lowered):
        plan = plan_experiment(hypothesis=q)
        return {"kind": "nl_analytics", "intent": "plan_experiment", "question": q, "answer": plan["notes"][0], "payload": plan}

    if re.search(r"\b(anomal\w*|contradiction\w*|dispersion\w*|what'?s wrong)\b", lowered):
        payload = analyze_anomalies(
            contradictions=context.get("contradictions") or [],
            risk=context.get("risk") or {},
            quotes=context.get("quotes") or [],
            portfolio=context.get("portfolio") or {},
        )
        return {"kind": "nl_analytics", "intent": "anomaly_analysis", "question": q, "answer": payload["summary"], "payload": payload}

    if re.search(r"\b(explain|how does|describe)\b.*\b(strateg|arb)", lowered) or "strategy" in lowered:
        research = context.get("research") or {}
        metrics = {}
        experiments = (research.get("experiments") or {}).get("recent") or []
        if experiments:
            metrics = experiments[0].get("metrics") or {}
        payload = explain_strategy(
            metrics=metrics,
            governance=research.get("governance") or {},
            opportunities=context.get("opportunities") or [],
        )
        return {"kind": "nl_analytics", "intent": "explain_strategy", "question": q, "answer": payload["summary"], "payload": payload}

    if re.search(r"\b(pnl|p&l|equity|portfolio|drawdown)\b", lowered):
        portfolio = context.get("portfolio") or {}
        equity = portfolio.get("equity")
        dd = portfolio.get("drawdown_pct")
        cash = portfolio.get("cash")
        answer = f"Equity={equity}, cash={cash}, drawdown_pct={dd}."
        return {
            "kind": "nl_analytics",
            "intent": "portfolio_snapshot",
            "question": q,
            "answer": answer,
            "payload": {"portfolio": portfolio},
        }

    if re.search(r"\b(ontology|prediction market|settlement)\b", lowered):
        ontology = context.get("ontology") or {}
        answer = (
            f"Ontology nodes/edges snapshot={ontology.get('graph')}; "
            f"prediction markets={ontology.get('prediction_markets')}; "
            f"contradictions={ontology.get('contradictions')}."
        )
        return {"kind": "nl_analytics", "intent": "ontology_status", "question": q, "answer": answer, "payload": ontology}

    return {
        "kind": "nl_analytics",
        "intent": "help",
        "question": q,
        "answer": (
            "I can explain strategies, plan experiments, analyze anomalies, "
            "summarize portfolio/ontology state, or draft governed strategy stubs. "
            "I cannot disable risk, enable live trading, or handle signing keys."
        ),
        "payload": {
            "examples": [
                "Explain the cross-venue arbitrage strategy",
                "Plan an experiment for edge stability",
                "What anomalies are present?",
                "What is portfolio drawdown?",
            ]
        },
    }
