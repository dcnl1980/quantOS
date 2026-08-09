"""Anomaly analysis over ontology contradictions, risk, and market dispersion."""
from __future__ import annotations

from typing import Any


def analyze_anomalies(
    contradictions: list[dict[str, Any]] | None = None,
    risk: dict[str, Any] | None = None,
    quotes: list[dict[str, Any]] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contradictions = contradictions or []
    risk = risk or {}
    quotes = quotes or []
    portfolio = portfolio or {}

    findings: list[dict[str, Any]] = []
    for c in contradictions[:50]:
        findings.append({
            "source": "ontology",
            "severity": c.get("severity", "info"),
            "kind": c.get("kind"),
            "message": c.get("message"),
            "nodes": c.get("nodes", []),
        })

    if risk.get("halted"):
        findings.append({
            "source": "risk",
            "severity": "critical",
            "kind": "circuit_breaker_halted",
            "message": f"Risk engine halted ({risk.get('rejections', 0)} rejections).",
            "nodes": [],
        })
    elif int(risk.get("rejections") or 0) >= 10:
        findings.append({
            "source": "risk",
            "severity": "warning",
            "kind": "elevated_rejections",
            "message": f"Elevated risk rejections: {risk.get('rejections')}.",
            "nodes": [],
        })

    dd = portfolio.get("drawdown_pct")
    if dd is not None and float(dd) >= 3.0:
        findings.append({
            "source": "portfolio",
            "severity": "warning",
            "kind": "drawdown_pressure",
            "message": f"Portfolio drawdown {dd}% approaching guardrails.",
            "nodes": [],
        })

    by_symbol: dict[str, list[float]] = {}
    for q in quotes:
        if q.get("symbol") and q.get("mid"):
            by_symbol.setdefault(q["symbol"], []).append(float(q["mid"]))
    for symbol, mids in by_symbol.items():
        if len(mids) < 2:
            continue
        lo, hi = min(mids), max(mids)
        ref = (lo + hi) / 2.0
        if ref <= 0:
            continue
        bps = ((hi - lo) / ref) * 10_000
        if bps >= 25:
            findings.append({
                "source": "market",
                "severity": "critical" if bps >= 80 else "warning",
                "kind": "quote_dispersion",
                "message": f"{symbol} mid dispersion {bps:.1f} bp.",
                "nodes": [f"symbol:{symbol}"],
            })

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: severity_rank.get(str(f.get("severity")), 9))

    if not findings:
        summary = "No material anomalies detected in ontology, risk, or quote dispersion."
    else:
        top = findings[0]
        summary = f"{len(findings)} anomal{'y' if len(findings)==1 else 'ies'}; top={top.get('kind')} ({top.get('severity')})."

    return {
        "kind": "anomaly_analysis",
        "summary": summary,
        "count": len(findings),
        "findings": findings,
        "recommended_actions": _actions(findings),
        "advisory": True,
        "execution_authority": False,
    }


def _actions(findings: list[dict[str, Any]]) -> list[str]:
    actions = [
        "Keep execution behind deterministic risk; do not widen limits from copilot advice.",
    ]
    kinds = {f.get("kind") for f in findings}
    if "complement_violation" in kinds:
        actions.append("Re-normalize prediction-market YES/NO probabilities and re-scan ontology.")
    if "quote_dispersion" in kinds or "cross_venue_dispersion" in kinds:
        actions.append("Confirm fee/slippage model and freshness before treating dispersion as edge.")
    if "circuit_breaker_halted" in kinds:
        actions.append("Inspect rejection reasons; reset circuit breaker only after operator review.")
    if "drawdown_pressure" in kinds:
        actions.append("Pause auto-execute and review Strategy Factory promotion status.")
    return actions
