import json
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from .config import settings
engine=create_async_engine(settings.database_url,pool_pre_ping=True)
async def ping_db():
    try:
        async with engine.connect() as c:await c.execute(text("select 1"))
        return True
    except Exception:return False
async def persist_opportunity(op):
    try:
        async with engine.begin() as c:
            await c.execute(text("""insert into opportunities
            (id,symbol,type,buy_venue,sell_venue,buy_price,sell_price,gross_edge_bps,net_edge_bps,confidence,max_notional,observed_at,metadata)
            values (:id,:symbol,:type,:buy_venue,:sell_venue,:buy_price,:sell_price,:gross_edge_bps,:net_edge_bps,:confidence,:max_notional,:observed_at,cast(:metadata as jsonb))
            on conflict(id) do nothing"""),{**op,"metadata":json.dumps(op.get("metadata",{}))})
    except Exception:pass
async def persist_fill(f):
    try:
        async with engine.begin() as c:
            await c.execute(text("""insert into fills
            (id,order_id,venue,symbol,side,quantity,price,fee,strategy,opportunity_id,ts)
            values (:id,:order_id,:venue,:symbol,:side,:quantity,:price,:fee,:strategy,:opportunity_id,:ts)
            on conflict(id) do nothing"""),f)
    except Exception:pass
