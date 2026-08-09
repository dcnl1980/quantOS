"""Detect semantic contradictions across the market ontology."""
from __future__ import annotations

from typing import Any
import uuid

from .prediction import PredictionMarket, normalize_market_probabilities
from .types import Contradiction, ContradictionSeverity, EdgeType


class ContradictionDetector:
    def __init__(
        self,
        complement_tolerance: float = 0.02,
        dispersion_warning_bps: float = 25.0,
        dispersion_critical_bps: float = 80.0,
    ):
        self.complement_tolerance = complement_tolerance
        self.dispersion_warning_bps = dispersion_warning_bps
        self.dispersion_critical_bps = dispersion_critical_bps

    def scan(
        self,
        graph: dict[str, Any],
        markets: list[PredictionMarket],
        quotes: list[dict[str, Any]] | None = None,
        basis: dict[str, Any] | None = None,
    ) -> list[Contradiction]:
        findings: list[Contradiction] = []
        findings.extend(self._prediction_contradictions(markets))
        findings.extend(self._quote_dispersion(quotes or []))
        findings.extend(self._settlement_gaps(graph, markets))
        findings.extend(self._basis_gaps(graph, basis or {}))
        findings.extend(self._missing_hedge_edges(graph))
        return findings

    def _prediction_contradictions(self, markets: list[PredictionMarket]) -> list[Contradiction]:
        out: list[Contradiction] = []
        for market in markets:
            mid = f"pm:{market.market_id}"
            for outcome in market.outcomes:
                if outcome.probability < 0 or outcome.probability > 1:
                    out.append(
                        Contradiction(
                            id=_cid(),
                            kind="probability_out_of_range",
                            severity=ContradictionSeverity.CRITICAL.value,
                            message=f"{market.market_id}/{outcome.label} probability {outcome.probability} outside [0,1]",
                            nodes=[mid, f"outcome:{outcome.outcome_id}"],
                            evidence={"probability": outcome.probability},
                        )
                    )
                if outcome.bid is not None and outcome.ask is not None and outcome.bid > outcome.ask:
                    out.append(
                        Contradiction(
                            id=_cid(),
                            kind="inverted_outcome_book",
                            severity=ContradictionSeverity.WARNING.value,
                            message=f"{market.market_id}/{outcome.label} bid > ask",
                            nodes=[f"outcome:{outcome.outcome_id}"],
                            evidence={"bid": outcome.bid, "ask": outcome.ask},
                        )
                    )

            norm = normalize_market_probabilities(market)
            gap = norm.get("complement_gap")
            if gap is not None and gap > self.complement_tolerance:
                severity = (
                    ContradictionSeverity.CRITICAL.value
                    if gap > self.complement_tolerance * 3
                    else ContradictionSeverity.WARNING.value
                )
                out.append(
                    Contradiction(
                        id=_cid(),
                        kind="complement_violation",
                        severity=severity,
                        message=f"{market.market_id} YES+NO deviate from 1 by {gap:.4f}",
                        nodes=[mid],
                        evidence={"complement_gap": gap, "raw": norm["raw"], "tolerance": self.complement_tolerance},
                    )
                )

            if not market.settlement_source:
                out.append(
                    Contradiction(
                        id=_cid(),
                        kind="missing_settlement_source",
                        severity=ContradictionSeverity.CRITICAL.value,
                        message=f"{market.market_id} has no settlement source",
                        nodes=[mid],
                    )
                )
        return out

    def _quote_dispersion(self, quotes: list[dict[str, Any]]) -> list[Contradiction]:
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for q in quotes:
            symbol = q.get("symbol")
            mid = q.get("mid")
            if not symbol or mid is None or mid <= 0:
                continue
            by_symbol.setdefault(symbol, []).append(q)

        out: list[Contradiction] = []
        for symbol, rows in by_symbol.items():
            if len(rows) < 2:
                continue
            mids = [float(r["mid"]) for r in rows]
            lo, hi = min(mids), max(mids)
            mid_ref = (lo + hi) / 2.0
            if mid_ref <= 0:
                continue
            dispersion_bps = ((hi - lo) / mid_ref) * 10_000
            if dispersion_bps < self.dispersion_warning_bps:
                continue
            severity = (
                ContradictionSeverity.CRITICAL.value
                if dispersion_bps >= self.dispersion_critical_bps
                else ContradictionSeverity.WARNING.value
            )
            venues = [r.get("venue") for r in rows]
            out.append(
                Contradiction(
                    id=_cid(),
                    kind="cross_venue_dispersion",
                    severity=severity,
                    message=f"{symbol} mid dispersion {dispersion_bps:.1f} bp across {venues}",
                    nodes=[f"symbol:{symbol}"] + [f"venue:{v}" for v in venues if v],
                    evidence={
                        "dispersion_bps": dispersion_bps,
                        "mids": {r.get("venue"): r.get("mid") for r in rows},
                        "warning_bps": self.dispersion_warning_bps,
                        "critical_bps": self.dispersion_critical_bps,
                    },
                )
            )
        return out

    def _settlement_gaps(
        self,
        graph: dict[str, Any],
        markets: list[PredictionMarket],
    ) -> list[Contradiction]:
        node_ids = {n["id"] for n in graph.get("nodes", [])}
        out: list[Contradiction] = []
        for market in markets:
            settle = f"settlement:{market.settlement_source}"
            # Settlement node always exists after graph build; flag orphan oracle refs
            # when settlement kind is oracle but underlying instrument is absent.
            uid = f"underlying:{market.underlying}"
            if uid not in node_ids:
                out.append(
                    Contradiction(
                        id=_cid(),
                        kind="unknown_underlying",
                        severity=ContradictionSeverity.WARNING.value,
                        message=f"{market.market_id} references unknown underlying {market.underlying}",
                        nodes=[f"pm:{market.market_id}", uid],
                    )
                )
            if settle not in node_ids:
                out.append(
                    Contradiction(
                        id=_cid(),
                        kind="orphan_settlement",
                        severity=ContradictionSeverity.WARNING.value,
                        message=f"{market.market_id} settlement {market.settlement_source} not in graph",
                        nodes=[f"pm:{market.market_id}", settle],
                    )
                )
        return out

    def _basis_gaps(self, graph: dict[str, Any], basis: dict[str, Any]) -> list[Contradiction]:
        currencies = {n["id"] for n in graph.get("nodes", []) if n.get("type") == "currency"}
        edges = graph.get("edges", [])
        has_basis = any(e.get("type") == EdgeType.BASIS.value for e in edges)
        out: list[Contradiction] = []
        if "currency:USDT" in currencies and "currency:USD" in currencies and not has_basis:
            out.append(
                Contradiction(
                    id=_cid(),
                    kind="missing_basis_edge",
                    severity=ContradictionSeverity.WARNING.value,
                    message="USDT and USD present without BASIS edge",
                    nodes=["currency:USDT", "currency:USD"],
                )
            )
        bps = basis.get("basis_bps")
        if bps is not None and abs(float(bps)) > 100:
            out.append(
                Contradiction(
                    id=_cid(),
                    kind="extreme_basis",
                    severity=ContradictionSeverity.WARNING.value,
                    message=f"USDT/USD basis {bps} bp is extreme",
                    nodes=["currency:USDT", "currency:USD"],
                    evidence={"basis_bps": bps},
                )
            )
        return out

    def _missing_hedge_edges(self, graph: dict[str, Any]) -> list[Contradiction]:
        """Warn when multiple instruments share an underlying but no HEDGES edge exists."""
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        derived: dict[str, list[str]] = {}
        for e in edges:
            if e.get("type") == EdgeType.DERIVED_FROM.value and str(e.get("source", "")).startswith("symbol:"):
                derived.setdefault(e["target"], []).append(e["source"])

        hedge_pairs = {
            frozenset((e["source"], e["target"]))
            for e in edges
            if e.get("type") == EdgeType.HEDGES.value
        }
        out: list[Contradiction] = []
        underlyings = {n["id"]: n for n in nodes if n.get("type") == "underlying"}
        for uid, symbols in derived.items():
            if uid not in underlyings or len(symbols) < 2:
                continue
            for i, a in enumerate(symbols):
                for b in symbols[i + 1 :]:
                    if frozenset((a, b)) not in hedge_pairs:
                        out.append(
                            Contradiction(
                                id=_cid(),
                                kind="missing_hedge_relation",
                                severity=ContradictionSeverity.INFO.value,
                                message=f"{a} and {b} share {uid} without HEDGES edge",
                                nodes=[a, b, uid],
                            )
                        )
        return out


def _cid() -> str:
    return f"cx_{uuid.uuid4().hex[:12]}"
