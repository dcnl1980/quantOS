import asyncio
import time
import uuid
from collections import deque
from dataclasses import asdict

from quant_os.market_state import MarketState
from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.strategies.lead_lag import LeadLagDetector
from quant_os.risk import RiskEngine, RiskConfig
from quant_os.broker import PaperBroker
from quant_os.models import Side, OrderRequest, Fill

from .config import settings
from .events import EventBus
from .engine_client import NativeExecutionClient
from .adapters.simulator import SimulatorAdapter
from .adapters.binance import BinanceBookTickerAdapter
from .adapters.coinbase import CoinbaseTickerAdapter
from .db import persist_opportunity, persist_fill

class QuantRuntime:
    def __init__(self):
        self.state = MarketState()
        self.bus = EventBus()
        self.costs = CostModel(settings.fees, settings.default_slippage_bps)
        self.arb = CrossVenueArbitrage(self.costs, settings.min_net_edge_bps)
        self.leadlag = LeadLagDetector()

        # Python fallback engine remains useful for unit tests and single-process development.
        self.risk = RiskEngine(RiskConfig(
            settings.max_order_notional,
            settings.max_symbol_exposure,
            settings.max_venue_exposure,
            settings.max_daily_loss,
            settings.max_drawdown_pct,
            settings.max_slippage_bps,
            settings.min_net_edge_bps,
            settings.circuit_breaker_rejections,
        ))
        self.broker = PaperBroker(
            settings.initial_cash, settings.fees, settings.default_slippage_bps
        )

        self.native = (
            NativeExecutionClient(
                settings.execution_engine_host,
                settings.execution_engine_port,
                settings.execution_timeout_ms,
            )
            if settings.native_execution else None
        )
        self.native_identity = None
        self.tasks = []
        self.opportunities = deque(maxlen=500)
        self.fills = deque(maxlen=1000)
        self.started = time.time()
        self.quote_count = 0
        self.opportunity_count = 0
        self.trade_count = 0
        self.last_exec_ns = {}
        self.engine_latencies_ns = deque(maxlen=2000)

    async def start(self):
        if self.native:
            # Native execution is a hard dependency when explicitly selected.
            last_error = None
            for _ in range(30):
                try:
                    pong = await self.native.ping()
                    self.native_identity = pong.get("engine", settings.execution_engine)
                    break
                except Exception as e:
                    last_error = e
                    await asyncio.sleep(.25)
            else:
                raise RuntimeError(f"native execution engine failed readiness: {last_error}")

        if settings.market_mode.lower() == "simulator":
            adapters = [
                SimulatorAdapter(
                    settings.symbol_list,
                    settings.sim_tick_ms,
                    settings.sim_arbitrage_probability,
                )
            ]
        else:
            adapters = []
            if "binance" in settings.venue_list:
                adapters.append(BinanceBookTickerAdapter(settings.symbol_list))
            if "coinbase" in settings.venue_list:
                adapters.append(CoinbaseTickerAdapter(settings.symbol_list))
            if not adapters:
                raise RuntimeError("MARKET_MODE=live but no supported LIVE_VENUES configured")

        for adapter in adapters:
            self.tasks.append(asyncio.create_task(self.consume(adapter)))

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.native:
            await self.native.close()

    async def consume(self, adapter):
        async for q in adapter.stream():
            self.quote_count += 1
            await self.state.update(q)
            await self.bus.publish({"type": "quote", "data": q.to_dict()})
            await self.scan(q.symbol)

    async def marks(self):
        return {q.symbol: q.mid for q in await self.state.all_quotes()}

    def can_execute_route(self, op):
        route = (op.symbol, op.buy_venue, op.sell_venue)
        now = time.monotonic_ns()
        last = self.last_exec_ns.get(route, 0)
        wait_ns = settings.min_execution_interval_ms * 1_000_000
        if now - last < wait_ns:
            return False
        self.last_exec_ns[route] = now
        return True

    async def scan(self, symbol):
        quotes = await self.state.for_symbol(symbol)
        for op in self.arb.scan(quotes)[:2]:
            self.opportunity_count += 1
            self.opportunities.appendleft(op)
            d = op.to_dict()
            await self.bus.publish({"type": "opportunity", "data": d})
            asyncio.create_task(persist_opportunity(d))
            if settings.paper_auto_execute and self.can_execute_route(op):
                await self.paper_execute(op)

        # Lead/lag remains analysis-only.
        histories = {q.venue: await self.state.history(q.venue, symbol, 25) for q in quotes}
        for op in self.leadlag.scan(histories)[:1]:
            self.opportunities.appendleft(op)
            await self.bus.publish({"type": "analysis_opportunity", "data": op.to_dict()})

    async def paper_execute(self, op):
        if self.native:
            result = await self.native.execute_arbitrage(
                op,
                settings.paper_order_notional,
                settings.fees,
                settings.default_slippage_bps,
            )
            self.engine_latencies_ns.append(int(result.get("latency_ns", 0)))
            await self.bus.publish({
                "type": "risk_decision",
                "data": {
                    "opportunity_id": op.id,
                    "allowed": result["allowed"],
                    "reason": result["reason"],
                    "approved_notional": result.get("approved_notional", 0),
                    "engine_latency_ns": result.get("latency_ns", 0),
                    "engine": self.native_identity,
                },
            })
            if not result["allowed"]:
                return

            qty = float(result["quantity"])
            common = dict(
                symbol=op.symbol,
                quantity=qty,
                strategy=self.arb.name,
                opportunity_id=op.id,
            )
            fills = [
                Fill(
                    order_id=str(uuid.uuid4()), venue=op.buy_venue, side=Side.BUY,
                    price=float(result["buy_exec_price"]), fee=float(result["buy_fee"]),
                    **common
                ),
                Fill(
                    order_id=str(uuid.uuid4()), venue=op.sell_venue, side=Side.SELL,
                    price=float(result["sell_exec_price"]), fee=float(result["sell_fee"]),
                    **common
                ),
            ]
            for f in fills:
                fd = f.to_dict()
                fd["engine_latency_ns"] = result.get("latency_ns", 0)
                fd["trade_pnl"] = result.get("trade_pnl", 0)
                self.fills.append(f)
                await self.bus.publish({"type": "fill", "data": fd})
                asyncio.create_task(persist_fill(f.to_dict()))

            self.trade_count += 1
            portfolio = await self.native.snapshot()
            await self.bus.publish({"type": "portfolio", "data": portfolio})
            return

        # Single-process Python fallback.
        p = self.broker.snapshot(await self.marks())
        d = self.risk.evaluate(
            op, p, settings.paper_order_notional, settings.default_slippage_bps
        )
        await self.bus.publish({
            "type": "risk_decision",
            "data": {
                "opportunity_id": op.id,
                "allowed": d.allowed,
                "reason": d.reason,
                "approved_notional": d.approved_notional,
                "engine": "python",
            },
        })
        if not d.allowed:
            return

        q = d.approved_notional / op.buy_price
        orders = [
            OrderRequest(op.buy_venue, op.symbol, Side.BUY, q, op.buy_price, self.arb.name, op.id),
            OrderRequest(op.sell_venue, op.symbol, Side.SELL, q, op.sell_price, self.arb.name, op.id),
        ]
        for o in orders:
            f = self.broker.execute(o)
            self.fills.append(f)
            fd = f.to_dict()
            await self.bus.publish({"type": "fill", "data": fd})
            asyncio.create_task(persist_fill(fd))
        self.trade_count += 1
        await self.bus.publish({
            "type": "portfolio",
            "data": asdict(self.broker.snapshot(await self.marks())),
        })

    async def portfolio_snapshot(self):
        if self.native:
            return await self.native.snapshot()
        return asdict(self.broker.snapshot(await self.marks()))

    async def risk_snapshot(self):
        if self.native:
            s = await self.native.snapshot()
            return {"halted": s["halted"], "rejections": s["rejection_count"]}
        return {"halted": self.risk.halted, "rejections": self.risk.rejections}

    async def reset_circuit_breaker(self):
        if self.native:
            return await self.native.reset_circuit_breaker()
        self.risk.reset_circuit_breaker()
        return {"ok": True}

    async def snapshot(self):
        portfolio = await self.portfolio_snapshot()
        risk = await self.risk_snapshot()
        return {
            "mode": settings.market_mode,
            "execution_engine": self.native_identity or "python",
            "execution_transport": "tcp-native" if self.native else "in-process",
            "execution": {
                "engine": self.native_identity or "python",
                "last_latency_ns": self.engine_latencies_ns[-1] if self.engine_latencies_ns else 0,
                "avg_latency_ns": (
                    int(sum(self.engine_latencies_ns) / len(self.engine_latencies_ns))
                    if self.engine_latencies_ns else 0
                ),
                "samples": len(self.engine_latencies_ns),
            },
            "uptime_seconds": round(time.time() - self.started, 1),
            "stats": {
                "quotes": self.quote_count,
                "opportunities": self.opportunity_count,
                "trades": self.trade_count,
            },
            "risk": risk,
            "portfolio": portfolio,
            "quotes": [q.to_dict() for q in await self.state.all_quotes()],
            "opportunities": [o.to_dict() for o in list(self.opportunities)[:50]],
            "fills": [f.to_dict() for f in list(self.fills)[-50:]][::-1],
        }

runtime = QuantRuntime()
