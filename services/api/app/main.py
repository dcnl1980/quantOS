import math
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from quant_os.models import Quote
from quant_os.backtest import ArbitrageBacktester

from .config import settings
from .runtime import runtime
from .db import ping_db


@asynccontextmanager
async def lifespan(app):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
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
    base = runtime.registry.graph()
    nodes = {n["id"]: n for n in base["nodes"]}
    edges = list(base["edges"])
    for q in await runtime.state.all_quotes():
        sid = f"symbol:{q.symbol}"
        vid = f"venue:{q.venue}"
        nodes.setdefault(sid, {"id": sid, "type": "instrument", "label": q.symbol})
        nodes.setdefault(vid, {"id": vid, "type": "venue", "label": q.venue})
        edges.append({"source": sid, "target": vid, "type": "LISTED_ON", "live": True})
    for op in list(runtime.opportunities)[:100]:
        if op.type.value != "cross_venue":
            continue
        a, b = f"venue:{op.buy_venue}", f"venue:{op.sell_venue}"
        edges.append({
            "source": a,
            "target": b,
            "type": "ARBITRAGE_WITH",
            "symbol": op.symbol,
            "net_edge_bps": op.net_edge_bps,
        })
    basis = runtime.basis.to_dict()
    edges.append({
        "source": "currency:USDT",
        "target": "currency:USD",
        "type": "BASIS",
        "usdt_usd": basis["usdt_usd"],
        "basis_bps": basis["basis_bps"],
    })
    nodes.setdefault("currency:USDT", {"id": "currency:USDT", "type": "currency", "label": "USDT"})
    nodes.setdefault("currency:USD", {"id": "currency:USD", "type": "currency", "label": "USD"})
    return {"nodes": list(nodes.values()), "edges": edges}


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
    rng = random.Random(7)
    base = 118000
    batches = []
    for i in range(max(100, min(ticks, 100000))):
        base *= math.exp(rng.gauss(0, .00012))
        dis = rng.uniform(14, 42) if rng.random() < .06 else rng.uniform(-1, 1)
        now = datetime.now(timezone.utc) + timedelta(milliseconds=i * 100)

        def q(v, off):
            mid = base * (1 + off / 10000)
            return Quote(v, "BTCUSDT", mid * .99995, mid * 1.00005, 2, 2, now, now, i)

        batches.append([q("sim_a", 0), q("sim_b", dis)])
    return ArbitrageBacktester(runtime.arb, notional).run(batches).to_dict()


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
