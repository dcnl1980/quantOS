"""Market ontology facade: graph + prediction markets + contradiction scan."""
from __future__ import annotations

from typing import Any

from quant_os.instrument_registry import InstrumentRegistry

from .contradictions import ContradictionDetector
from .graph import MarketGraphBuilder
from .prediction import PredictionMarket, PredictionMarketBook, make_binary_market
from .types import Contradiction


class MarketOntology:
    def __init__(
        self,
        registry: InstrumentRegistry,
        seed_demo_markets: bool = True,
        detector: ContradictionDetector | None = None,
    ):
        self.registry = registry
        self.prediction_book = PredictionMarketBook()
        if seed_demo_markets:
            self.prediction_book.seed_demo()
        self.detector = detector or ContradictionDetector()
        self._last_graph: dict[str, Any] | None = None
        self._last_contradictions: list[Contradiction] = []

    def register_prediction_market(
        self,
        question: str,
        venue: str,
        settlement_source: str,
        underlying: str,
        yes_probability: float,
        market_id: str | None = None,
        fee_bps: float = 100.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market = make_binary_market(
            question=question,
            venue=venue,
            settlement_source=settlement_source,
            underlying=underlying,
            yes_probability=yes_probability,
            fee_bps=fee_bps,
            market_id=market_id,
            metadata=metadata,
        )
        self.prediction_book.upsert(market)
        return market.to_dict()

    def upsert_market(self, market: PredictionMarket) -> dict[str, Any]:
        return self.prediction_book.upsert(market).to_dict()

    def update_outcome_probability(
        self,
        market_id: str,
        outcome_label: str,
        probability: float,
    ) -> dict[str, Any] | None:
        market = self.prediction_book.update_probability(market_id, outcome_label, probability)
        return market.to_dict() if market else None

    def build_graph(
        self,
        quotes: list[dict[str, Any]] | None = None,
        opportunities: list[dict[str, Any]] | None = None,
        basis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        builder = MarketGraphBuilder(self.registry, self.prediction_book)
        graph = builder.build(
            quotes=quotes or [],
            opportunities=opportunities or [],
            basis=basis or {},
        )
        self._last_graph = graph
        return graph

    def scan(
        self,
        quotes: list[dict[str, Any]] | None = None,
        opportunities: list[dict[str, Any]] | None = None,
        basis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        graph = self.build_graph(quotes=quotes, opportunities=opportunities, basis=basis)
        findings = self.detector.scan(
            graph=graph,
            markets=self.prediction_book.list(),
            quotes=quotes or [],
            basis=basis or {},
        )
        self._last_contradictions = findings
        by_severity: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for c in findings:
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
            by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
        return {
            "graph": graph,
            "contradictions": [c.to_dict() for c in findings],
            "summary": {
                "count": len(findings),
                "by_severity": by_severity,
                "by_kind": by_kind,
                "prediction_markets": len(self.prediction_book.list()),
            },
        }

    def contradictions(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._last_contradictions]

    def snapshot(self) -> dict[str, Any]:
        graph = self._last_graph or {"nodes": [], "edges": [], "stats": {}}
        return {
            "enabled": True,
            "graph": {
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("edges", [])),
                "edge_types": (graph.get("stats") or {}).get("edge_types", {}),
            },
            "prediction_markets": {
                "count": len(self.prediction_book.list()),
                "markets": [m.market_id for m in self.prediction_book.list()],
            },
            "contradictions": {
                "count": len(self._last_contradictions),
                "by_severity": _count_attr(self._last_contradictions, "severity"),
                "by_kind": _count_attr(self._last_contradictions, "kind"),
            },
        }


def _count_attr(items: list[Contradiction], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        key = getattr(item, attr)
        out[key] = out.get(key, 0) + 1
    return out
