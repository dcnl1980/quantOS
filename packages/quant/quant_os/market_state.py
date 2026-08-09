import asyncio
from collections import defaultdict, deque
from .models import Quote

class MarketState:
    def __init__(self, history_size=1000):
        self.quotes={}
        self.hist=defaultdict(lambda: deque(maxlen=history_size))
        self.lock=asyncio.Lock()

    async def update(self,q:Quote):
        async with self.lock:
            self.quotes[(q.venue,q.symbol)]=q
            self.hist[(q.venue,q.symbol)].append(q)

    async def for_symbol(self,symbol):
        async with self.lock:
            return [q for (_,s),q in self.quotes.items() if s==symbol]

    async def all_quotes(self):
        async with self.lock:
            return list(self.quotes.values())

    async def history(self,venue,symbol,n=100):
        async with self.lock:
            return list(self.hist[(venue,symbol)])[-n:]
