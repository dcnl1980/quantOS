import asyncio,json
from datetime import datetime,timezone
import websockets
from quant_os.models import Quote
class CoinbaseTickerAdapter:
    URL="wss://advanced-trade-ws.coinbase.com"
    def __init__(self,symbols):
        self.symbols=symbols;self.products=[self.product(s) for s in symbols];self.reverse={self.product(s):s for s in symbols}
    @staticmethod
    def product(s):
        return s[:-4]+"-USD" if s.endswith("USDT") else (s[:-3]+"-USD" if s.endswith("USD") else s)
    async def stream(self):
        backoff=1
        while True:
            try:
                async with websockets.connect(self.URL,ping_interval=20,ping_timeout=20,max_queue=2048) as ws:
                    await ws.send(json.dumps({"type":"subscribe","product_ids":self.products,"channel":"ticker"}));backoff=1
                    async for raw in ws:
                        o=json.loads(raw)
                        for e in o.get("events",[]):
                            for t in e.get("tickers",[]):
                                pid=t.get("product_id");bid=t.get("best_bid");ask=t.get("best_ask")
                                if not pid or not bid or not ask:continue
                                now=datetime.now(timezone.utc)
                                yield Quote("coinbase",self.reverse.get(pid,pid),float(bid),float(ask),0,0,now,now)
            except asyncio.CancelledError:raise
            except Exception:
                await asyncio.sleep(backoff);backoff=min(backoff*2,30)
