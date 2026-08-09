"""Strategy and opportunity explanations (deterministic, advisory)."""
from __future__ import annotations

from typing import Any


def explain_strategy(
    strategy_id: str = "cross_venue_arbitrage",
    metrics: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = metrics or {}
    governance = governance or {}
    opportunities = opportunities or []
    status = (governance.get("statuses") or {}).get(strategy_id, "candidate")
    recent = [o for o in opportunities if str(o.get("type", "")).lower().replace("-", "_") in {"cross_venue", "crossvenue"}][:5]

    bullets = [
        f"{strategy_id} looks for cost-adjusted mid dislocations across venues.",
        "Net edge must clear fees, slippage, and min_net_edge_bps before risk evaluation.",
        "Approved notionals still pass through the deterministic risk engine; AI cannot soften those checks.",
    ]
    if metrics:
        bullets.append(
            "Latest research metrics: "
            f"OOS PnL={metrics.get('oos_net_pnl', 'n/a')}, "
            f"stability={metrics.get('stability_score', 'n/a')}, "
            f"MC p05={metrics.get('p05_net_pnl', 'n/a')}."
        )
    if recent:
        top = max(recent, key=lambda o: float(o.get("net_edge_bps") or 0))
        bullets.append(
            f"Strongest recent opportunity: {top.get('symbol')} "
            f"{top.get('buy_venue')}→{top.get('sell_venue')} "
            f"+{top.get('net_edge_bps')} bp."
        )
    bullets.append(f"Governance status: {status}.")

    return {
        "kind": "strategy_explanation",
        "strategy_id": strategy_id,
        "status": status,
        "summary": " ".join(bullets[:2]),
        "bullets": bullets,
        "advisory": True,
        "execution_authority": False,
    }


def explain_fill(fill: dict[str, Any]) -> dict[str, Any]:
    side = str(fill.get("side", "")).upper()
    return {
        "kind": "fill_explanation",
        "summary": (
            f"{side} {fill.get('quantity')} {fill.get('symbol')} on {fill.get('venue')} "
            f"at {fill.get('price')} (strategy={fill.get('strategy') or fill.get('strategy_id') or 'n/a'})."
        ),
        "bullets": [
            "Fills are produced by paper/shadow/testnet brokers after risk approval.",
            "Copilot can narrate fills but cannot reverse, cancel, or re-route venue orders.",
        ],
        "fill": fill,
        "advisory": True,
        "execution_authority": False,
    }
