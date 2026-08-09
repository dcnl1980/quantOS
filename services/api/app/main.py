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
async def root():return {"name":settings.app_name,"mode":settings.market_mode,"paper_trading":True,"live_trading_enabled":settings.enable_live_trading,"docs":"/docs"}
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
async def reset_cb():runtime.risk.reset_circuit_breaker();return {"ok":True}

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
