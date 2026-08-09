from quant_os.instrument_registry import InstrumentRegistry
from quant_os.ontology import (
    MarketOntology,
    ContradictionDetector,
    PredictionMarket,
    OutcomeQuote,
    normalize_market_probabilities,
    make_binary_market,
)


def test_graph_includes_core_edge_types():
    ontology = MarketOntology(InstrumentRegistry.default(["BTCUSDT", "BTCUSD"]), seed_demo_markets=True)
    graph = ontology.build_graph(
        quotes=[
            {"symbol": "BTCUSDT", "venue": "binance", "bid": 100, "ask": 100.1, "mid": 100.05},
            {"symbol": "BTCUSDT", "venue": "coinbase", "bid": 100.2, "ask": 100.3, "mid": 100.25},
        ],
        opportunities=[{
            "id": "op1",
            "type": "cross_venue",
            "symbol": "BTCUSDT",
            "buy_venue": "binance",
            "sell_venue": "coinbase",
            "net_edge_bps": 12.0,
        }],
        basis={"usdt_usd": 1.0, "basis_bps": 0.0, "source": "config"},
    )
    types = {e["type"] for e in graph["edges"]}
    for required in {
        "LISTED_ON",
        "DERIVED_FROM",
        "PRICED_IN",
        "SETTLES_FROM",
        "HEDGES",
        "CORRELATED_WITH",
        "ARBITRAGE_WITH",
        "BASIS",
        "COMPLEMENTS",
        "OUTCOME_OF",
        "DETECTED_BY",
    }:
        assert required in types
    assert graph["stats"]["prediction_markets"] >= 3
    assert graph["stats"]["nodes"] > 10


def test_binary_complement_normalization():
    market = make_binary_market(
        question="test",
        venue="polymarket",
        settlement_source="spot:binance:BTCUSDT",
        underlying="BTC",
        yes_probability=0.6,
    )
    # Force inconsistent NO, then normalize.
    market.outcomes[1].probability = 0.7
    norm = normalize_market_probabilities(market)
    assert norm["method"] == "binary_complement"
    assert abs(norm["normalized"][market.outcomes[0].outcome_id] - 0.6) < 1e-9
    assert abs(norm["normalized"][market.outcomes[1].outcome_id] - 0.4) < 1e-9
    assert abs(norm["complement_gap"] - 0.3) < 1e-9


def test_contradiction_complement_and_dispersion():
    ontology = MarketOntology(InstrumentRegistry.default(["BTCUSDT"]), seed_demo_markets=False)
    bad = PredictionMarket(
        market_id="pm_bad",
        question="broken market",
        venue="polymarket",
        settlement_source="spot:binance:BTCUSDT",
        underlying="BTC",
        outcomes=[
            OutcomeQuote("pm_bad:YES", "YES", 0.8),
            OutcomeQuote("pm_bad:NO", "NO", 0.8),
        ],
    )
    ontology.upsert_market(bad)
    scan = ontology.scan(
        quotes=[
            {"symbol": "BTCUSDT", "venue": "binance", "mid": 100.0},
            {"symbol": "BTCUSDT", "venue": "coinbase", "mid": 101.0},
        ],
        basis={"usdt_usd": 1.0, "basis_bps": 0.0},
    )
    kinds = {c["kind"] for c in scan["contradictions"]}
    assert "complement_violation" in kinds
    assert "cross_venue_dispersion" in kinds
    assert scan["summary"]["count"] >= 2


def test_register_and_update_probability():
    ontology = MarketOntology(InstrumentRegistry.default(), seed_demo_markets=False)
    created = ontology.register_prediction_market(
        question="Will BTC pump?",
        venue="polymarket",
        settlement_source="spot:binance:BTCUSDT",
        underlying="BTC",
        yes_probability=0.4,
        market_id="pm_custom",
    )
    assert created["market_id"] == "pm_custom"
    updated = ontology.update_outcome_probability("pm_custom", "YES", 0.55)
    assert updated is not None
    yes = next(o for o in updated["outcomes"] if o["label"] == "YES")
    no = next(o for o in updated["outcomes"] if o["label"] == "NO")
    assert abs(yes["probability"] - 0.55) < 1e-9
    assert abs(no["probability"] - 0.45) < 1e-9


def test_detector_probability_out_of_range():
    detector = ContradictionDetector()
    market = PredictionMarket(
        market_id="pm_oor",
        question="oor",
        venue="polymarket",
        settlement_source="x",
        underlying="BTC",
        outcomes=[OutcomeQuote("a", "YES", 1.5), OutcomeQuote("b", "NO", -0.2)],
    )
    findings = detector.scan({"nodes": [], "edges": []}, [market], quotes=[], basis={})
    kinds = {f.kind for f in findings}
    assert "probability_out_of_range" in kinds
