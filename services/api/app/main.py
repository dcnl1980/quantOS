import math,random
from contextlib import asynccontextmanager
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST
from quant_os.models import Quote
from quant_os.backtest import ArbitrageBacktester
from .config import settings
from .runtime import runtime
from .db import ping_db

@asynccontextmanager
async def lifespan(app):
    await runtime.start();yield;await runtime.stop()

app=FastAPI(title=settings.app_name,version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.api_cors_origins.split(",")],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "mode": settings.market_mode,
        "execution_engine": settings.execution_engine,
        "paper_trading": True,
        "live_trading_enabled": settings.enable_live_trading,
        "docs": "/docs",
    }
@app.get("/health")
async def health():return {"ok":True,"mode":settings.market_mode}
@app.get("/ready")
async def ready():return {"ok":True,"database":await ping_db(),"feed_tasks":len(runtime.tasks)}
@app.get("/api/v1/snapshot")
async def snapshot():return await runtime.snapshot()
@app.get("/api/v1/quotes")
async def quotes():return [q.to_dict() for q in await runtime.state.all_quotes()]
@app.get("/api/v1/opportunities")
async def opportunities(limit:int=50):return [o.to_dict() for o in list(runtime.opportunities)[:max(1,min(limit,500))]]
@app.get("/api/v1/portfolio")
async def portfolio():return (await runtime.snapshot())["portfolio"]
@app.get("/api/v1/fills")
async def fills(limit:int=100):return [f.to_dict() for f in runtime.broker.fills[-max(1,min(limit,1000)):]][::-1]
@app.post("/api/v1/risk/reset-circuit-breaker")
async def reset_cb():
    return await runtime.reset_circuit_breaker()


@app.get("/api/v1/strategies")
async def strategies():
    return [
        {
            "id": "cross_venue_arbitrage",
            "status": "active",
            "auto_execute": settings.paper_auto_execute,
            "description": "Best-ask versus best-bid cross-venue dislocation after modeled fees and slippage.",
            "min_net_edge_bps": settings.min_net_edge_bps,
            "execution": settings.execution_engine,
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
    }

@app.get("/api/v1/engine")
async def engine_status():
    if runtime.native:
        return {
            "configured": settings.execution_engine,
            "identity": runtime.native_identity,
            "transport": "persistent-private-tcp",
            "health": await runtime.native.ping(),
            "portfolio": await runtime.native.snapshot(),
        }
    return {
        "configured": "python",
        "identity": "python",
        "transport": "in-process",
        "portfolio": await runtime.portfolio_snapshot(),
    }

@app.get("/api/v1/market-graph")
async def market_graph():
    quotes = await runtime.state.all_quotes()
    nodes = {}
    edges = []
    for q in quotes:
        sid = f"symbol:{q.symbol}"
        vid = f"venue:{q.venue}"
        nodes[sid] = {"id": sid, "type": "instrument", "label": q.symbol}
        nodes[vid] = {"id": vid, "type": "venue", "label": q.venue}
        edges.append({"source": sid, "target": vid, "type": "LISTED_ON"})
    for op in list(runtime.opportunities)[:100]:
        if op.type.value != "cross_venue":
            continue
        a, b = f"venue:{op.buy_venue}", f"venue:{op.sell_venue}"
        edges.append({
            "source": a, "target": b, "type": "ARBITRAGE_WITH",
            "symbol": op.symbol, "net_edge_bps": op.net_edge_bps,
        })
    return {"nodes": list(nodes.values()), "edges": edges}

@app.post("/api/v1/backtest/demo")
async def backtest(ticks:int=2000,notional:float=1000):
    rng=random.Random(7);base=118000;batches=[]
    for i in range(max(100,min(ticks,100000))):
        base*=math.exp(rng.gauss(0,.00012));dis=rng.uniform(14,42) if rng.random()<.06 else rng.uniform(-1,1);now=datetime.now(timezone.utc)+timedelta(milliseconds=i*100)
        def q(v,off):
            mid=base*(1+off/10000);return Quote(v,"BTCUSDT",mid*.99995,mid*1.00005,2,2,now,now,i)
        batches.append([q("sim_a",0),q("sim_b",dis)])
    return ArbitrageBacktester(runtime.arb,notional).run(batches).to_dict()

@app.get("/metrics")
async def metrics():return PlainTextResponse(generate_latest().decode(),media_type=CONTENT_TYPE_LATEST)

@app.websocket("/ws")
async def websocket(ws:WebSocket):
    await ws.accept();q=runtime.bus.subscribe()
    try:
        await ws.send_json({"type":"snapshot","data":await runtime.snapshot()})
        while True:await ws.send_json(await q.get())
    except WebSocketDisconnect:pass
    finally:runtime.bus.unsubscribe(q)
