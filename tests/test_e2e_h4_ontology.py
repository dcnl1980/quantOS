"""End-to-end H4 ontology through MarketOntology and FastAPI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "quant"))
sys.path.insert(0, str(ROOT / "services" / "api"))

os.environ.setdefault("EXECUTION_ENGINE", "python")
os.environ.setdefault("MARKET_MODE", "simulator")
os.environ.setdefault("EXECUTION_MODE", "paper")
os.environ.setdefault("ENABLE_L2_BOOKS", "false")
os.environ.setdefault("DATA_PLANE_ENABLED", "true")
os.environ.setdefault("BUS_BACKEND", "memory")
os.environ.setdefault("ARCHIVE_BACKEND", "memory")
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("PAPER_AUTO_EXECUTE", "false")
os.environ.setdefault("SIM_TICK_MS", "250")

from quant_os.instrument_registry import InstrumentRegistry  # noqa: E402
from quant_os.ontology import MarketOntology, OutcomeQuote, PredictionMarket  # noqa: E402
from app.adapters.polymarket import PolymarketOntologyBridge  # noqa: E402


def test_e2e_ontology_scan_and_bridge():
    ontology = MarketOntology(InstrumentRegistry.default(["BTCUSDT", "ETHUSDT"]), seed_demo_markets=True)
    bridge = PolymarketOntologyBridge(ontology)
    bridge.ingest_binary_market(
        market_id="pm_bridge",
        question="Bridge ingest works?",
        yes_probability=0.33,
        settlement_source="spot:binance:BTCUSDT",
        underlying="BTC",
    )
    # Inject a complement violation for deterministic detection.
    ontology.upsert_market(
        PredictionMarket(
            market_id="pm_broken",
            question="Broken complement",
            venue="polymarket",
            settlement_source="spot:binance:ETHUSDT",
            underlying="ETH",
            outcomes=[
                OutcomeQuote("pm_broken:YES", "YES", 0.9),
                OutcomeQuote("pm_broken:NO", "NO", 0.9),
            ],
        )
    )
    scan = ontology.scan(
        quotes=[
            {"symbol": "BTCUSDT", "venue": "binance", "mid": 50000},
            {"symbol": "BTCUSDT", "venue": "coinbase", "mid": 50150},
        ],
        opportunities=[{
            "id": "op-e2e",
            "type": "cross_venue",
            "symbol": "BTCUSDT",
            "buy_venue": "binance",
            "sell_venue": "coinbase",
            "net_edge_bps": 18.0,
        }],
        basis={"usdt_usd": 0.999, "basis_bps": 10.0, "source": "config"},
    )
    assert scan["graph"]["stats"]["nodes"] > 0
    assert any(m["market_id"] == "pm_bridge" for m in ontology.prediction_book.to_list())
    assert any(c["kind"] == "complement_violation" for c in scan["contradictions"])
    snap = ontology.snapshot()
    assert snap["prediction_markets"]["count"] >= 4
    assert snap["contradictions"]["count"] >= 1


def test_e2e_ontology_api_endpoints():
    from fastapi.testclient import TestClient
    from app.config import settings
    from app.main import app
    from app.runtime import runtime

    settings.paper_auto_execute = False
    settings.enable_l2_books = False
    settings.otel_enabled = False

    with TestClient(app) as client:
        plane = client.get("/api/v1/ontology")
        assert plane.status_code == 200
        body = plane.json()
        assert body["enabled"] is True
        assert body["prediction_markets"]["count"] >= 1

        graph = client.get("/api/v1/ontology/graph")
        assert graph.status_code == 200
        g = graph.json()
        assert "nodes" in g and "edges" in g
        assert len(g["nodes"]) > 0

        legacy = client.get("/api/v1/market-graph")
        assert legacy.status_code == 200
        assert "nodes" in legacy.json()

        markets = client.get("/api/v1/ontology/prediction-markets")
        assert markets.status_code == 200
        assert isinstance(markets.json(), list)

        created = client.post(
            "/api/v1/ontology/prediction-markets",
            params={
                "question": "API market?",
                "underlying": "BTC",
                "settlement_source": "spot:binance:BTCUSDT",
                "yes_probability": 0.44,
                "market_id": "pm_api",
            },
        )
        assert created.status_code == 200
        assert created.json()["market_id"] == "pm_api"

        updated = client.post(
            "/api/v1/ontology/prediction-markets/pm_api/probability",
            params={"outcome_label": "YES", "probability": 0.61},
        )
        assert updated.status_code == 200
        yes = next(o for o in updated.json()["outcomes"] if o["label"] == "YES")
        assert abs(yes["probability"] - 0.61) < 1e-9

        scan = client.post("/api/v1/ontology/scan")
        assert scan.status_code == 200
        assert "contradictions" in scan.json()
        assert "summary" in scan.json()

        cx = client.get("/api/v1/ontology/contradictions")
        assert cx.status_code == 200
        assert "contradictions" in cx.json()

        snap = client.get("/api/v1/snapshot")
        assert snap.status_code == 200
        assert "ontology" in snap.json()
