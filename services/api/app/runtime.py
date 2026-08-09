import asyncio,time
from collections import deque
from dataclasses import asdict
from quant_os.market_state import MarketState
from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.strategies.lead_lag import LeadLagDetector
from quant_os.risk import RiskEngine,RiskConfig
from quant_os.broker import PaperBroker
from quant_os.models import Side,OrderRequest
from .config import settings
from .events import EventBus
from .adapters.simulator import SimulatorAdapter
from .adapters.binance import BinanceBookTickerAdapter
from .adapters.coinbase import CoinbaseTickerAdapter
from .db import persist_opportunity,persist_fill

class QuantRuntime:
    def __init__(self):
        self.state=MarketState();self.bus=EventBus();self.costs=CostModel(settings.fees,settings.default_slippage_bps)
        self.arb=CrossVenueArbitrage(self.costs,settings.min_net_edge_bps);self.leadlag=LeadLagDetector()
        self.risk=RiskEngine(RiskConfig(settings.max_order_notional,settings.max_symbol_exposure,settings.max_venue_exposure,settings.max_daily_loss,settings.max_drawdown_pct,settings.max_slippage_bps,settings.min_net_edge_bps,settings.circuit_breaker_rejections))
        self.broker=PaperBroker(settings.initial_cash,settings.fees,settings.default_slippage_bps)
        self.tasks=[];self.opportunities=deque(maxlen=500);self.started=time.time();self.quote_count=0;self.opportunity_count=0;self.trade_count=0

    async def start(self):
        if settings.market_mode.lower()=="simulator":
            adapters=[SimulatorAdapter(settings.symbol_list,settings.sim_tick_ms,settings.sim_arbitrage_probability)]
        else:
            adapters=[]
            if "binance" in settings.venue_list:adapters.append(BinanceBookTickerAdapter(settings.symbol_list))
            if "coinbase" in settings.venue_list:adapters.append(CoinbaseTickerAdapter(settings.symbol_list))
        for a in adapters:self.tasks.append(asyncio.create_task(self.consume(a)))

    async def stop(self):
        for t in self.tasks:t.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)

    async def consume(self,a):
        async for q in a.stream():
            self.quote_count+=1;await self.state.update(q);await self.bus.publish({"type":"quote","data":q.to_dict()});await self.scan(q.symbol)

    async def marks(self):
        return {q.symbol:q.mid for q in await self.state.all_quotes()}

    async def scan(self,symbol):
        quotes=await self.state.for_symbol(symbol)
        for op in self.arb.scan(quotes)[:2]:
            self.opportunity_count+=1;self.opportunities.appendleft(op);d=op.to_dict()
            await self.bus.publish({"type":"opportunity","data":d});asyncio.create_task(persist_opportunity(d))
            if settings.paper_auto_execute:await self.paper_execute(op)
        histories={q.venue:await self.state.history(q.venue,symbol,25) for q in quotes}
        for op in self.leadlag.scan(histories)[:1]:
            self.opportunities.appendleft(op);await self.bus.publish({"type":"analysis_opportunity","data":op.to_dict()})

    async def paper_execute(self,op):
        p=self.broker.snapshot(await self.marks());d=self.risk.evaluate(op,p,settings.paper_order_notional,settings.default_slippage_bps)
        await self.bus.publish({"type":"risk_decision","data":{"opportunity_id":op.id,"allowed":d.allowed,"reason":d.reason,"approved_notional":d.approved_notional}})
        if not d.allowed:return
        q=d.approved_notional/op.buy_price
        orders=[OrderRequest(op.buy_venue,op.symbol,Side.BUY,q,op.buy_price,self.arb.name,op.id),OrderRequest(op.sell_venue,op.symbol,Side.SELL,q,op.sell_price,self.arb.name,op.id)]
        for o in orders:
            f=self.broker.execute(o);fd=f.to_dict();await self.bus.publish({"type":"fill","data":fd});asyncio.create_task(persist_fill(fd))
        self.trade_count+=1
        await self.bus.publish({"type":"portfolio","data":asdict(self.broker.snapshot(await self.marks()))})

    async def snapshot(self):
        return {"mode":settings.market_mode,"uptime_seconds":round(time.time()-self.started,1),
        "stats":{"quotes":self.quote_count,"opportunities":self.opportunity_count,"trades":self.trade_count},
        "risk":{"halted":self.risk.halted,"rejections":self.risk.rejections},
        "portfolio":asdict(self.broker.snapshot(await self.marks())),
        "quotes":[q.to_dict() for q in await self.state.all_quotes()],
        "opportunities":[o.to_dict() for o in list(self.opportunities)[:50]],
        "fills":[f.to_dict() for f in self.broker.fills[-50:]][::-1]}
runtime=QuantRuntime()
