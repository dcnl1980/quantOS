"""Build the instrument/venue/underlying/settlement ontology graph."""
from __future__ import annotations

from typing import Any, Iterable

from quant_os.instrument_registry import InstrumentRegistry

from .prediction import PredictionMarket, PredictionMarketBook
from .types import EdgeType, GraphEdge, GraphNode, NodeType


class MarketGraphBuilder:
    """Compose registry, live quotes, opportunities, basis, and prediction markets."""

    def __init__(
        self,
        registry: InstrumentRegistry,
        prediction_book: PredictionMarketBook | None = None,
        correlate_threshold_bps: float = 5.0,
    ):
        self.registry = registry
        self.prediction_book = prediction_book or PredictionMarketBook()
        self.correlate_threshold_bps = correlate_threshold_bps

    def build(
        self,
        quotes: Iterable[dict[str, Any]] | None = None,
        opportunities: Iterable[dict[str, Any]] | None = None,
        basis: dict[str, Any] | None = None,
        detectors: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        self._add_registry(nodes, edges)
        self._add_quotes(nodes, edges, quotes or [])
        self._add_hedges_and_correlations(nodes, edges)
        self._add_opportunities(nodes, edges, opportunities or [])
        self._add_basis(nodes, edges, basis or {})
        self._add_prediction_markets(nodes, edges)
        self._add_detectors(nodes, edges, detectors or ["cross_venue_arbitrage", "lead_lag"])

        return {
            "nodes": [n.to_dict() for n in nodes.values()],
            "edges": [e.to_dict() for e in edges],
            "stats": {
                "nodes": len(nodes),
                "edges": len(edges),
                "prediction_markets": len(self.prediction_book.list()),
                "edge_types": _count_edge_types(edges),
            },
        }

    def _add_registry(self, nodes: dict[str, GraphNode], edges: list[GraphEdge]) -> None:
        for inst in self.registry.to_list():
            sid = f"symbol:{inst['symbol']}"
            nodes[sid] = GraphNode(
                sid,
                NodeType.INSTRUMENT.value,
                inst["symbol"],
                {"base": inst["base"], "quote": inst["quote"], "settlement": inst["settlement"]},
            )
            uid = f"underlying:{inst['underlying']}"
            nodes[uid] = GraphNode(uid, NodeType.UNDERLYING.value, inst["underlying"])
            edges.append(GraphEdge(sid, uid, EdgeType.DERIVED_FROM.value))

            qid = f"currency:{inst['quote']}"
            nodes[qid] = GraphNode(qid, NodeType.CURRENCY.value, inst["quote"])
            edges.append(GraphEdge(sid, qid, EdgeType.PRICED_IN.value))

            settle_id = f"settlement:{inst['settlement']}"
            nodes[settle_id] = GraphNode(
                settle_id,
                NodeType.SETTLEMENT_SOURCE.value,
                inst["settlement"],
                {"kind": "currency"},
            )
            edges.append(GraphEdge(sid, settle_id, EdgeType.SETTLES_FROM.value))

            for listing in inst.get("listings", []):
                vid = f"venue:{listing['venue']}"
                nodes[vid] = GraphNode(vid, NodeType.VENUE.value, listing["venue"])
                edges.append(
                    GraphEdge(
                        sid,
                        vid,
                        EdgeType.LISTED_ON.value,
                        {
                            "venue_symbol": listing["venue_symbol"],
                            "tick_size": listing.get("tick_size"),
                            "lot_size": listing.get("lot_size"),
                        },
                    )
                )

    def _add_quotes(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
        quotes: Iterable[dict[str, Any]],
    ) -> None:
        for q in quotes:
            symbol = q.get("symbol")
            venue = q.get("venue")
            if not symbol or not venue:
                continue
            sid = f"symbol:{symbol}"
            vid = f"venue:{venue}"
            nodes.setdefault(sid, GraphNode(sid, NodeType.INSTRUMENT.value, symbol))
            nodes.setdefault(vid, GraphNode(vid, NodeType.VENUE.value, venue))
            edges.append(
                GraphEdge(
                    sid,
                    vid,
                    EdgeType.LISTED_ON.value,
                    {
                        "live": True,
                        "bid": q.get("bid"),
                        "ask": q.get("ask"),
                        "mid": q.get("mid"),
                    },
                )
            )

    def _add_hedges_and_correlations(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        """Same-underlying instruments hedge each other; same-base pairs correlate."""
        by_underlying: dict[str, list[str]] = {}
        by_base: dict[str, list[str]] = {}
        for inst in self.registry.to_list():
            sid = f"symbol:{inst['symbol']}"
            by_underlying.setdefault(inst["underlying"], []).append(sid)
            by_base.setdefault(inst["base"], []).append(sid)

        for group in by_underlying.values():
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    edges.append(
                        GraphEdge(a, b, EdgeType.HEDGES.value, {"reason": "shared_underlying"})
                    )
                    edges.append(
                        GraphEdge(b, a, EdgeType.HEDGES.value, {"reason": "shared_underlying"})
                    )

        for group in by_base.values():
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    edges.append(
                        GraphEdge(
                            a,
                            b,
                            EdgeType.CORRELATED_WITH.value,
                            {"reason": "shared_base", "threshold_bps": self.correlate_threshold_bps},
                        )
                    )

    def _add_opportunities(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
        opportunities: Iterable[dict[str, Any]],
    ) -> None:
        for op in opportunities:
            otype = str(op.get("type", "")).lower().replace("-", "_")
            if otype not in {"cross_venue", "crossvenue"}:
                continue
            buy = op.get("buy_venue")
            sell = op.get("sell_venue")
            if not buy or not sell:
                continue
            a, b = f"venue:{buy}", f"venue:{sell}"
            nodes.setdefault(a, GraphNode(a, NodeType.VENUE.value, buy))
            nodes.setdefault(b, GraphNode(b, NodeType.VENUE.value, sell))
            edges.append(
                GraphEdge(
                    a,
                    b,
                    EdgeType.ARBITRAGE_WITH.value,
                    {
                        "symbol": op.get("symbol"),
                        "net_edge_bps": op.get("net_edge_bps"),
                        "opportunity_id": op.get("id"),
                    },
                )
            )
            sid = f"symbol:{op.get('symbol')}"
            if op.get("symbol"):
                edges.append(
                    GraphEdge(
                        sid,
                        "detector:cross_venue_arbitrage",
                        EdgeType.DETECTED_BY.value,
                        {"net_edge_bps": op.get("net_edge_bps")},
                    )
                )
                edges.append(
                    GraphEdge(
                        "detector:cross_venue_arbitrage",
                        sid,
                        EdgeType.CAUSED_BY.value,
                        {"reason": "price_dispersion"},
                    )
                )

    def _add_basis(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
        basis: dict[str, Any],
    ) -> None:
        usdt = "currency:USDT"
        usd = "currency:USD"
        nodes.setdefault(usdt, GraphNode(usdt, NodeType.CURRENCY.value, "USDT"))
        nodes.setdefault(usd, GraphNode(usd, NodeType.CURRENCY.value, "USD"))
        edges.append(
            GraphEdge(
                usdt,
                usd,
                EdgeType.BASIS.value,
                {
                    "usdt_usd": basis.get("usdt_usd"),
                    "basis_bps": basis.get("basis_bps"),
                    "source": basis.get("source"),
                },
            )
        )

    def _add_prediction_markets(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        for market in self.prediction_book.list():
            mid = f"pm:{market.market_id}"
            nodes[mid] = GraphNode(
                mid,
                NodeType.PREDICTION_MARKET.value,
                market.question,
                {
                    "market_id": market.market_id,
                    "venue": market.venue,
                    "status": market.status,
                    "underlying": market.underlying,
                },
            )
            vid = f"venue:{market.venue}"
            nodes.setdefault(vid, GraphNode(vid, NodeType.VENUE.value, market.venue))
            edges.append(GraphEdge(mid, vid, EdgeType.LISTED_ON.value))

            uid = f"underlying:{market.underlying}"
            nodes.setdefault(uid, GraphNode(uid, NodeType.UNDERLYING.value, market.underlying))
            edges.append(GraphEdge(mid, uid, EdgeType.DERIVED_FROM.value))

            settle = f"settlement:{market.settlement_source}"
            nodes.setdefault(
                settle,
                GraphNode(
                    settle,
                    NodeType.SETTLEMENT_SOURCE.value,
                    market.settlement_source,
                    {"kind": "oracle"},
                ),
            )
            edges.append(GraphEdge(mid, settle, EdgeType.SETTLES_FROM.value))

            outcome_nodes: list[str] = []
            for outcome in market.outcomes:
                oid = f"outcome:{outcome.outcome_id}"
                outcome_nodes.append(oid)
                nodes[oid] = GraphNode(
                    oid,
                    NodeType.OUTCOME.value,
                    outcome.label,
                    {
                        "probability": outcome.probability,
                        "bid": outcome.bid,
                        "ask": outcome.ask,
                        "fee_bps": outcome.fee_bps,
                        "market_id": market.market_id,
                    },
                )
                edges.append(GraphEdge(oid, mid, EdgeType.OUTCOME_OF.value))

            # Binary complements
            labels = {o.outcome_id: o.label.upper() for o in market.outcomes}
            yes = next((oid for oid, lab in labels.items() if lab == "YES"), None)
            no = next((oid for oid, lab in labels.items() if lab == "NO"), None)
            if yes and no:
                edges.append(
                    GraphEdge(
                        f"outcome:{yes}",
                        f"outcome:{no}",
                        EdgeType.COMPLEMENTS.value,
                        {"constraint": "p_yes + p_no ~= 1"},
                    )
                )

    def _add_detectors(
        self,
        nodes: dict[str, GraphNode],
        edges: list[GraphEdge],
        detectors: Iterable[str],
    ) -> None:
        for name in detectors:
            did = f"detector:{name}"
            nodes.setdefault(
                did,
                GraphNode(did, "detector", name, {"plane": "strategy"}),
            )


def _count_edge_types(edges: list[GraphEdge]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in edges:
        out[e.type] = out.get(e.type, 0) + 1
    return out


def seed_graph_from_markets(markets: list[PredictionMarket]) -> PredictionMarketBook:
    book = PredictionMarketBook()
    for m in markets:
        book.upsert(m)
    return book
