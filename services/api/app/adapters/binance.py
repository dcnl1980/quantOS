import asyncio,json
from datetime import datetime,timezone
import websockets
from quant_os.models import Quote
class BinanceBookTickerAdapter:
    BASE="wss://stream.binance.com:9443/stream?streams="
    def __init__(self,symbols):self.symbols=symbols
    async def stream(self):
        url=self.BASE+"/".join(f"{s.lower()}@bookTicker" for s in self.symbols);backoff=1
        while True:
            try:
                async with websockets.connect(url,ping_interval=20,ping_timeout=20,max_queue=2048) as ws:
                    backoff=1
                    async for raw in ws:
                        d=json.loads(raw);d=d.get("data",d)
                        if not {"s","b","a"}.issubset(d):continue
                        now=datetime.now(timezone.utc)
                        yield Quote("binance",d["s"].upper(),float(d["b"]),float(d["a"]),float(d.get("B",0) or 0),float(d.get("A",0) or 0),now,now,int(d["u"]) if d.get("u") is not None else None)
            except asyncio.CancelledError:raise
            except Exception:
                await asyncio.sleep(backoff);backoff=min(backoff*2,30)
