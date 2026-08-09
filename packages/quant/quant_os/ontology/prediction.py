"""Prediction-market semantics: outcomes, complements, probability normalization."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass(slots=True)
class OutcomeQuote:
    outcome_id: str
    label: str  # YES / NO / custom
    probability: float
    bid: float | None = None
    ask: float | None = None
    fee_bps: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PredictionMarket:
    market_id: str
    question: str
    venue: str
    settlement_source: str
    underlying: str
    outcomes: list[OutcomeQuote] = field(default_factory=list)
    status: str = "open"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "venue": self.venue,
            "settlement_source": self.settlement_source,
            "underlying": self.underlying,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "status": self.status,
            "metadata": self.metadata,
            "normalized": normalize_market_probabilities(self),
        }


def clamp_probability(p: float) -> float:
    if p < 0.0:
        return 0.0
    if p > 1.0:
        return 1.0
    return float(p)


def normalize_market_probabilities(market: PredictionMarket) -> dict[str, Any]:
    """Normalize outcome probabilities and enforce binary YES/NO complement when present."""
    raw = {o.outcome_id: clamp_probability(o.probability) for o in market.outcomes}
    total = sum(raw.values()) or 0.0
    labels = {o.outcome_id: o.label.upper() for o in market.outcomes}
    yes_ids = [oid for oid, lab in labels.items() if lab == "YES"]
    no_ids = [oid for oid, lab in labels.items() if lab == "NO"]

    normalized = dict(raw)
    method = "identity"
    if len(yes_ids) == 1 and len(no_ids) == 1 and len(market.outcomes) == 2:
        y, n = yes_ids[0], no_ids[0]
        # Prefer YES as primary; NO is complement.
        y_p = clamp_probability(raw[y])
        normalized[y] = y_p
        normalized[n] = clamp_probability(1.0 - y_p)
        method = "binary_complement"
    elif total > 0 and abs(total - 1.0) > 1e-9:
        normalized = {k: v / total for k, v in raw.items()}
        method = "l1_rescale"

    complement_gap = None
    if len(yes_ids) == 1 and len(no_ids) == 1:
        complement_gap = abs(raw[yes_ids[0]] + raw[no_ids[0]] - 1.0)

    return {
        "method": method,
        "raw": raw,
        "normalized": normalized,
        "raw_sum": total,
        "complement_gap": complement_gap,
    }


def make_binary_market(
    question: str,
    venue: str,
    settlement_source: str,
    underlying: str,
    yes_probability: float,
    fee_bps: float = 100.0,
    market_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PredictionMarket:
    mid = market_id or f"pm_{uuid.uuid4().hex[:12]}"
    yes_p = clamp_probability(yes_probability)
    no_p = clamp_probability(1.0 - yes_p)
    return PredictionMarket(
        market_id=mid,
        question=question,
        venue=venue,
        settlement_source=settlement_source,
        underlying=underlying,
        outcomes=[
            OutcomeQuote(f"{mid}:YES", "YES", yes_p, bid=max(0.0, yes_p - 0.01), ask=min(1.0, yes_p + 0.01), fee_bps=fee_bps),
            OutcomeQuote(f"{mid}:NO", "NO", no_p, bid=max(0.0, no_p - 0.01), ask=min(1.0, no_p + 0.01), fee_bps=fee_bps),
        ],
        metadata=metadata or {},
    )


class PredictionMarketBook:
    def __init__(self):
        self._markets: dict[str, PredictionMarket] = {}

    def upsert(self, market: PredictionMarket) -> PredictionMarket:
        self._markets[market.market_id] = market
        return market

    def get(self, market_id: str) -> PredictionMarket | None:
        return self._markets.get(market_id)

    def list(self) -> list[PredictionMarket]:
        return list(self._markets.values())

    def update_probability(self, market_id: str, outcome_label: str, probability: float) -> PredictionMarket | None:
        market = self._markets.get(market_id)
        if not market:
            return None
        label = outcome_label.upper()
        for outcome in market.outcomes:
            if outcome.label.upper() == label:
                outcome.probability = clamp_probability(probability)
                if outcome.bid is not None:
                    outcome.bid = max(0.0, outcome.probability - 0.01)
                if outcome.ask is not None:
                    outcome.ask = min(1.0, outcome.probability + 0.01)
        # Keep binary complements consistent when YES moves.
        if label == "YES" and len(market.outcomes) == 2:
            yes_p = next(o.probability for o in market.outcomes if o.label.upper() == "YES")
            for outcome in market.outcomes:
                if outcome.label.upper() == "NO":
                    outcome.probability = clamp_probability(1.0 - yes_p)
                    if outcome.bid is not None:
                        outcome.bid = max(0.0, outcome.probability - 0.01)
                    if outcome.ask is not None:
                        outcome.ask = min(1.0, outcome.probability + 0.01)
        return market

    def to_list(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._markets.values()]

    def seed_demo(self) -> list[PredictionMarket]:
        demos = [
            make_binary_market(
                question="Will BTC close above $100k this month?",
                venue="polymarket",
                settlement_source="spot:binance:BTCUSDT",
                underlying="BTC",
                yes_probability=0.42,
                market_id="pm_btc_100k",
                metadata={"horizon": "month", "threshold": 100000},
            ),
            make_binary_market(
                question="Will ETH outperform BTC over the next 7 days?",
                venue="polymarket",
                settlement_source="relative:ETHUSDT/BTCUSDT",
                underlying="ETH",
                yes_probability=0.51,
                market_id="pm_eth_vs_btc",
                metadata={"horizon": "7d"},
            ),
            make_binary_market(
                question="Will SOL break $300 before quarter end?",
                venue="polymarket",
                settlement_source="spot:coinbase:SOL-USD",
                underlying="SOL",
                yes_probability=0.28,
                market_id="pm_sol_300",
                metadata={"horizon": "quarter", "threshold": 300},
            ),
        ]
        for m in demos:
            self.upsert(m)
        return demos
