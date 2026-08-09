import asyncio,math,random
from datetime import datetime,timezone
from quant_os.models import Quote
class SimulatorAdapter:
    def __init__(self,symbols,tick_ms=250,arb_probability=.08,seed=42):
        self.symbols=symbols;self.tick=tick_ms/1000;self.prob=arb_probability;self.rng=random.Random(seed);self.seq=0
        start={"BTCUSDT":118000,"ETHUSDT":3900,"SOLUSDT":185};self.prices={s:start.get(s,100) for s in symbols}
    async def stream(self):
        while True:
            self.seq+=1
            for s in self.symbols:
                p=self.prices[s]*math.exp(self.rng.gauss(0,.00015));self.prices[s]=p
                spread=self.rng.uniform(.5,2);dis=self.rng.uniform(12,45) if self.rng.random()<self.prob else self.rng.uniform(-1.5,1.5)
                for v,off in [("sim_a",0),("sim_b",dis)]:
                    mid=p*(1+off/10000);half=spread/2/10000;now=datetime.now(timezone.utc)
                    yield Quote(v,s,mid*(1-half),mid*(1+half),self.rng.uniform(.2,4),self.rng.uniform(.2,4),now,now,self.seq)
            await asyncio.sleep(self.tick)
