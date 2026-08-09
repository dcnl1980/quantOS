"""Polymarket adapter boundary with H4 prediction-market ontology semantics.

Production extension steps:
1) discover current markets and outcome token IDs from official market/CLOB APIs;
2) persist market -> outcome token -> settlement source semantics via MarketOntology;
3) subscribe to the official public market WebSocket with current asset IDs;
4) maintain L2 books from snapshots/deltas;
5) normalize outcome probabilities and model YES/NO complement constraints + fees.

Stale hard-coded token IDs are intentionally not included.
"""
from __future__ import annotations

from typing import Any

from quant_os.ontology import (
    MarketOntology,
    PredictionMarket,
    make_binary_market,
    normalize_market_probabilities,
)


class PolymarketOntologyBridge:
    """Maps discovered Polymarket markets into the shared ontology."""

    def __init__(self, ontology: MarketOntology, venue: str = "polymarket"):
        self.ontology = ontology
        self.venue = venue

    def ingest_binary_market(
        self,
        *,
        market_id: str,
        question: str,
        yes_probability: float,
        settlement_source: str,
        underlying: str,
        fee_bps: float = 100.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market = make_binary_market(
            question=question,
            venue=self.venue,
            settlement_source=settlement_source,
            underlying=underlying,
            yes_probability=yes_probability,
            fee_bps=fee_bps,
            market_id=market_id,
            metadata=metadata,
        )
        return self.ontology.upsert_market(market)

    def normalize(self, market: PredictionMarket) -> dict[str, Any]:
        return normalize_market_probabilities(market)
