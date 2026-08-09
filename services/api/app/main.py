from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from quant_os.backtest import ArbitrageBacktester

from .config import settings
from .runtime import runtime
from .db import ping_db


@asynccontextmanager
async def lifespan(app):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.api_cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "market_mode": settings.resolved_market_mode(),
        "execution_mode": settings.resolved_execution_mode(),
        "mode": settings.market_mode,
        "execution_engine": settings.execution_engine,
        "paper_trading": settings.resolved_execution_mode() == "paper",
        "shadow_trading": settings.is_shadow,
        "testnet_trading": settings.is_testnet,
        "live_trading_enabled": settings.enable_live_trading,
        "data_plane_enabled": settings.data_plane_enabled,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "market_mode": settings.resolved_market_mode(),
        "execution_mode": settings.resolved_execution_mode(),
    }


@app.get("/ready")
async def ready():
    return {
        "ok": True,
        "database": await ping_db(),
        "feed_tasks": len(runtime.tasks),
        "data_plane": runtime.data_bus.stats(),
    }


@app.get("/api/v1/snapshot")
async def snapshot():
    return await runtime.snapshot()


@app.get("/api/v1/quotes")
async def quotes():
    return [q.to_dict() for q in await runtime.state.all_quotes()]


@app.get("/api/v1/opportunities")
async def opportunities(limit: int = 50):
    return [o.to_dict() for o in list(runtime.opportunities)[: max(1, min(limit, 500))]]


@app.get("/api/v1/portfolio")
async def portfolio():
    return (await runtime.snapshot())["portfolio"]


@app.get("/api/v1/fills")
async def fills(limit: int = 100):
    n = max(1, min(limit, 1000))
    native = [f.to_dict() for f in list(runtime.fills)[-n:]][::-1]
    if native:
        return native
    return [f.to_dict() for f in runtime.broker.fills[-n:]][::-1]


@app.get("/api/v1/shadow-fills")
async def shadow_fills(limit: int = 100):
    n = max(1, min(limit, 1000))
    return [f.to_dict() for f in list(runtime.shadow_fills)[-n:]][::-1]


@app.post("/api/v1/risk/reset-circuit-breaker")
async def reset_cb():
    return await runtime.reset_circuit_breaker()


@app.get("/api/v1/strategies")
async def strategies():
    mode = settings.resolved_execution_mode()
    auto = (
        (mode == "paper" and settings.paper_auto_execute)
        or (mode == "testnet" and settings.testnet_auto_execute)
    )
    return [
        {
            "id": "cross_venue_arbitrage",
            "status": "active",
            "auto_execute": auto,
            "shadow": mode == "shadow",
            "testnet": mode == "testnet",
            "description": "Best-ask versus best-bid cross-venue dislocation after modeled fees and slippage.",
            "min_net_edge_bps": settings.min_net_edge_bps,
            "execution": "testnet-gateway" if mode == "testnet" else settings.execution_engine,
            "execution_mode": mode,
        },
        {
            "id": "lead_lag",
            "status": "active",
            "auto_execute": False,
            "description": "Short-window cross-venue lead/lag divergence. Analysis-only by design.",
        },
    ]


@app.get("/api/v1/risk/config")
async def risk_config():
    return {
        "min_net_edge_bps": settings.min_net_edge_bps,
        "max_order_notional": settings.max_order_notional,
        "max_symbol_exposure": settings.max_symbol_exposure,
        "max_venue_exposure": settings.max_venue_exposure,
        "max_daily_loss": settings.max_daily_loss,
        "max_drawdown_pct": settings.max_drawdown_pct,
        "max_slippage_bps": settings.max_slippage_bps,
        "circuit_breaker_rejections": settings.circuit_breaker_rejections,
        "min_execution_interval_ms": settings.min_execution_interval_ms,
        "execution_mode": settings.resolved_execution_mode(),
    }


@app.get("/api/v1/engine")
async def engine_status():
    if runtime.native:
        return {
            "configured": settings.execution_engine,
            "identity": runtime.native_identity,
            "transport": "persistent-private-tcp",
            "execution_mode": settings.resolved_execution_mode(),
            "health": await runtime.native.ping(),
            "portfolio": await runtime.native.snapshot(),
        }
    return {
        "configured": "python",
        "identity": "python",
        "transport": "in-process",
        "execution_mode": settings.resolved_execution_mode(),
        "portfolio": await runtime.portfolio_snapshot(),
    }


@app.get("/api/v1/market-graph")
async def market_graph():
    """Legacy alias for the H4 ontology graph."""
    return await runtime.ontology_graph()


@app.get("/api/v1/ontology")
async def ontology_plane():
    # Refresh summary counts without forcing a full contradiction rescan every poll.
    graph = await runtime.ontology_graph()
    snap = runtime.ontology.snapshot()
    snap["graph"] = {
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "edge_types": (graph.get("stats") or {}).get("edge_types", {}),
    }
    return snap


@app.get("/api/v1/ontology/graph")
async def ontology_graph():
    return await runtime.ontology_graph()


@app.get("/api/v1/ontology/prediction-markets")
async def ontology_prediction_markets():
    return runtime.ontology.prediction_book.to_list()


@app.post("/api/v1/ontology/prediction-markets")
async def ontology_register_prediction_market(
    question: str,
    venue: str = "polymarket",
    settlement_source: str = "spot:binance:BTCUSDT",
    underlying: str = "BTC",
    yes_probability: float = 0.5,
    market_id: str | None = None,
    fee_bps: float = 100.0,
):
    return runtime.ontology.register_prediction_market(
        question=question,
        venue=venue,
        settlement_source=settlement_source,
        underlying=underlying,
        yes_probability=yes_probability,
        market_id=market_id,
        fee_bps=fee_bps,
    )


@app.post("/api/v1/ontology/prediction-markets/{market_id}/probability")
async def ontology_update_probability(
    market_id: str,
    outcome_label: str = "YES",
    probability: float = 0.5,
):
    updated = runtime.ontology.update_outcome_probability(market_id, outcome_label, probability)
    if not updated:
        return {"ok": False, "reason": "unknown_market"}
    return updated


@app.get("/api/v1/ontology/contradictions")
async def ontology_contradictions():
    if not runtime.ontology.contradictions():
        scan = await runtime.ontology_scan()
        return {
            "contradictions": scan["contradictions"],
            "summary": scan["summary"],
        }
    return {
        "contradictions": runtime.ontology.contradictions(),
        "summary": runtime.ontology.snapshot()["contradictions"],
    }


@app.post("/api/v1/ontology/scan")
async def ontology_scan():
    return await runtime.ontology_scan()


@app.get("/api/v1/instruments")
async def instruments():
    return runtime.registry.to_list()


@app.get("/api/v1/orderbooks")
async def orderbooks():
    return runtime.books.snapshot()


@app.get("/api/v1/data-plane")
async def data_plane():
    return {
        "enabled": settings.data_plane_enabled,
        "bus": runtime.data_bus.stats(),
        "archive": runtime.archive.stats(),
        "telemetry": runtime.telemetry.stats(),
        "clock": runtime.clock.snapshot(),
        "basis": runtime.basis.to_dict(),
        "recent_ticks": runtime.archive.recent_ticks(20),
    }


@app.get("/api/v1/basis")
async def basis():
    return runtime.basis.to_dict()


@app.get("/api/v1/clock")
async def clock():
    return runtime.clock.snapshot()


@app.get("/api/v1/execution-plane")
async def execution_plane():
    snap = await runtime.snapshot()
    return snap["execution_plane"]


@app.get("/api/v1/orders")
async def orders():
    return runtime.gateway.fsm.snapshot()


@app.post("/api/v1/orders/{client_order_id}/cancel")
async def cancel_order(client_order_id: str):
    return await runtime.gateway.cancel_order(client_order_id)


@app.post("/api/v1/orders/{client_order_id}/replace")
async def replace_order(client_order_id: str, price: float, quantity: float | None = None):
    return await runtime.gateway.replace_order(client_order_id, price, quantity)


@app.get("/api/v1/inventory")
async def inventory():
    return runtime.inventory.to_dict()


@app.get("/api/v1/fee-tiers")
async def fee_tiers():
    return runtime.fee_schedule.to_dict()


@app.get("/api/v1/reconciliation")
async def reconciliation():
    return await runtime.gateway.reconcile_once() if settings.is_testnet else runtime.gateway.reconciler.to_dict()


@app.post("/api/v1/backtest/demo")
async def backtest(ticks: int = 2000, notional: float = 1000):
    # Keep legacy endpoint, but route through research dataset synthesizer.
    from quant_os.research import synthesize_arbitrage_batches
    dataset = synthesize_arbitrage_batches(ticks=max(100, min(ticks, 100000)), seed=7)
    return ArbitrageBacktester(runtime.arb, notional).run(dataset.batches).to_dict()


@app.get("/api/v1/research")
async def research_plane():
    return runtime.research.snapshot()


@app.post("/api/v1/research/walk-forward")
async def research_walk_forward(
    ticks: int = 2400,
    seed: int = 7,
    train_size: int = 800,
    test_size: int = 200,
    step: int = 200,
    min_net_edge_bps: float | None = None,
):
    params = {}
    if min_net_edge_bps is not None:
        params["min_net_edge_bps"] = min_net_edge_bps
    return runtime.research.run_walk_forward(
        ticks=ticks, seed=seed, train_size=train_size,
        test_size=test_size, step=step, params=params or None,
    )


@app.post("/api/v1/research/monte-carlo")
async def research_monte_carlo(
    ticks: int = 1500,
    seed: int = 7,
    runs: int = 40,
    min_net_edge_bps: float | None = None,
):
    params = {}
    if min_net_edge_bps is not None:
        params["min_net_edge_bps"] = min_net_edge_bps
    return runtime.research.run_monte_carlo(
        ticks=ticks, seed=seed, runs=runs, params=params or None,
    )


@app.post("/api/v1/research/sensitivity")
async def research_sensitivity(
    ticks: int = 1500,
    seed: int = 7,
    parameter: str = "min_net_edge_bps",
    values: str = "4,6,8,10,12,16,20",
):
    parsed = [float(x.strip()) for x in values.split(",") if x.strip()]
    return runtime.research.run_sensitivity(
        ticks=ticks, seed=seed, parameter=parameter, values=parsed,
    )


@app.post("/api/v1/research/suite")
async def research_suite(
    ticks: int = 2400,
    seed: int = 7,
    mc_runs: int = 30,
    stage: str = "paper",
    min_net_edge_bps: float | None = None,
):
    params = {}
    if min_net_edge_bps is not None:
        params["min_net_edge_bps"] = min_net_edge_bps
    return runtime.research.run_full_suite(
        ticks=ticks, seed=seed, mc_runs=mc_runs, params=params or None, stage=stage,
    )


@app.get("/api/v1/research/experiments")
async def research_experiments(limit: int = 50):
    return [e.to_dict() for e in runtime.research.experiments.list(limit)]


@app.get("/api/v1/research/experiments/{experiment_id}")
async def research_experiment(experiment_id: str):
    exp = runtime.research.experiments.get(experiment_id)
    if not exp:
        return {"ok": False, "reason": "unknown_experiment"}
    return exp.to_dict()


@app.post("/api/v1/research/promote/{experiment_id}")
async def research_promote(experiment_id: str, stage: str = "paper"):
    return runtime.research.promote(experiment_id, stage=stage)


@app.get("/api/v1/research/features")
async def research_features():
    return runtime.research.features.snapshot()


@app.get("/api/v1/research/governance")
async def research_governance():
    return runtime.research.governor.snapshot()


@app.get("/api/v1/copilot")
async def copilot_plane():
    return runtime.copilot.snapshot()


@app.post("/api/v1/copilot/explain")
async def copilot_explain(strategy_id: str = "cross_venue_arbitrage"):
    research = runtime.research.snapshot()
    metrics = {}
    recent = (research.get("experiments") or {}).get("recent") or []
    if recent:
        metrics = recent[0].get("metrics") or {}
    return runtime.copilot.explain_strategy(
        strategy_id=strategy_id,
        metrics=metrics,
        governance=research.get("governance") or {},
        opportunities=[o.to_dict() for o in list(runtime.opportunities)[:20]],
    )


@app.post("/api/v1/copilot/explain-fill")
async def copilot_explain_fill(fill_id: str | None = None):
    fills = list(runtime.fills)
    if not fills:
        return {"ok": False, "reason": "no_fills"}
    fill = fills[-1].to_dict()
    if fill_id:
        match = next((f.to_dict() for f in fills if f.id == fill_id), None)
        if not match:
            return {"ok": False, "reason": "unknown_fill"}
        fill = match
    return runtime.copilot.explain_fill(fill)


@app.post("/api/v1/copilot/plan-experiment")
async def copilot_plan_experiment(
    hypothesis: str,
    strategy_id: str = "cross_venue_arbitrage",
    focus: str = "edge_stability",
):
    return runtime.copilot.plan_experiment(
        hypothesis=hypothesis,
        strategy_id=strategy_id,
        focus=focus,
    )


@app.post("/api/v1/copilot/analyze")
async def copilot_analyze():
    ctx = await runtime.copilot_context()
    return runtime.copilot.analyze(
        contradictions=ctx["contradictions"],
        risk=ctx["risk"],
        quotes=ctx["quotes"],
        portfolio=ctx["portfolio"],
    )


@app.post("/api/v1/copilot/ask")
async def copilot_ask(question: str):
    ctx = await runtime.copilot_context()
    return runtime.copilot.ask(question, context=ctx)


@app.post("/api/v1/copilot/codegen")
async def copilot_codegen(
    name: str,
    kind: str = "cross_venue_arbitrage",
    hypothesis: str = "",
    min_net_edge_bps: float = 8.0,
):
    return runtime.copilot.codegen(
        name=name,
        kind=kind,
        hypothesis=hypothesis,
        min_net_edge_bps=min_net_edge_bps,
    )


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    q = runtime.bus.subscribe()
    try:
        await ws.send_json({"type": "snapshot", "data": await runtime.snapshot()})
        while True:
            await ws.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        runtime.bus.unsubscribe(q)
