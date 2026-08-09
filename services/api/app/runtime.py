import asyncio
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone

from quant_os.market_state import MarketState
from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.strategies.lead_lag import LeadLagDetector
from quant_os.risk import RiskEngine, RiskConfig
from quant_os.broker import PaperBroker
from quant_os.models import Side, OrderRequest, Fill, Quote
from quant_os.instrument_registry import InstrumentRegistry
from quant_os.basis import BasisModel
from quant_os.clock_telemetry import ClockTelemetry
from quant_os.orderbook import OrderBookRegistry
from quant_os.fee_tiers import FeeSchedule
from quant_os.inventory import InventoryAllocator
from quant_os.hedge import PartialFillHedgePolicy
from quant_os.live_broker import LiveBroker, LiveTradingDisabled

from .config import settings
from .events import EventBus
from .engine_client import NativeExecutionClient
from .adapters.simulator import SimulatorAdapter
from .adapters.binance import BinanceBookTickerAdapter
from .adapters.coinbase import CoinbaseTickerAdapter
from .adapters.binance_depth import BinanceDepthAdapter
from .db import persist_opportunity, persist_fill
from .dataplane import build_bus, build_archive, build_telemetry
from .execution import ExecutionGateway


class QuantRuntime:
    def __init__(self):
        self.state = MarketState()
        self.bus = EventBus()
        self.costs = CostModel(settings.fees, settings.default_slippage_bps)
        self.arb = CrossVenueArbitrage(self.costs, settings.min_net_edge_bps)
        self.leadlag = LeadLagDetector()

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
        self.shadow_fills = deque(maxlen=1000)
        self.started = time.time()
        self.quote_count = 0
        self.opportunity_count = 0
        self.trade_count = 0
        self.shadow_trade_count = 0
        self.last_exec_ns = {}
        self.engine_latencies_ns = deque(maxlen=2000)

        self.registry = InstrumentRegistry.default(settings.symbol_list)
        self.basis = BasisModel(usdt_usd=settings.usdt_usd_basis, source="config")
        self.clock = ClockTelemetry(stale_ms=settings.clock_stale_ms)
        self.books = OrderBookRegistry(depth=settings.l2_depth)
        self.data_bus = build_bus(
            settings.data_plane_enabled,
            settings.bus_backend,
            settings.kafka_bootstrap,
        )
        self.archive = build_archive(
            settings.data_plane_enabled,
            settings.archive_backend,
            settings.clickhouse_url,
            settings.clickhouse_database,
        )
        self.telemetry = build_telemetry(settings.otel_enabled)

        self.fee_schedule = FeeSchedule.default()
        self.fee_schedule.set_volume("binance", settings.fee_tier_volume_binance)
        self.fee_schedule.set_volume("coinbase", settings.fee_tier_volume_coinbase)
        self.inventory = InventoryAllocator(
            total_capital=settings.initial_cash,
            venue_weights=settings.inventory_weights,
        )
        self.gateway = ExecutionGateway(
            risk=self.risk,
            fee_schedule=self.fee_schedule,
            inventory=self.inventory,
            publish=self.bus.publish,
            hedge=PartialFillHedgePolicy(min_hedge_qty=settings.min_hedge_qty),
            partial_fill_ratio=settings.testnet_partial_fill_ratio,
        )
        self.live_broker_error: str | None = None

    async def start(self):
        await self.data_bus.start()
        await self.archive.start()

        mode = settings.resolved_execution_mode()
        if mode == "live":
            try:
                LiveBroker(
                    settings.enable_live_trading,
                    settings.live_trading_ack,
                    testnet_validated=False,
                )
            except (LiveTradingDisabled, NotImplementedError) as exc:
                self.live_broker_error = str(exc)

        if mode == "testnet":
            venues = settings.testnet_venue_list or ["sim_a", "sim_b"]
            await self.gateway.start(
                venues,
                settings.testnet_api_key,
                settings.testnet_api_secret,
            )

        # Native engine is the paper/shadow hot path. Testnet uses the H2 gateway instead.
        if self.native and mode != "testnet":
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

        market_mode = settings.resolved_market_mode()
        if market_mode == "simulator":
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
                if settings.enable_l2_books:
                    adapters.append(BinanceDepthAdapter(settings.symbol_list, settings.l2_depth))
            if "coinbase" in settings.venue_list:
                adapters.append(CoinbaseTickerAdapter(settings.symbol_list))
            if not adapters:
                raise RuntimeError("MARKET_MODE=live/shadow but no supported LIVE_VENUES configured")

        for adapter in adapters:
            if isinstance(adapter, BinanceDepthAdapter):
                self.tasks.append(asyncio.create_task(self.consume_book(adapter)))
            else:
                self.tasks.append(asyncio.create_task(self.consume(adapter)))

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.gateway.stop()
        await self.archive.stop()
        await self.data_bus.stop()
        if self.native:
            await self.native.close()

    def _normalize_quote(self, q: Quote) -> Quote:
        quote_ccy = self.registry.quote_currency(q.symbol) or "USDT"
        # Coinbase listings are USD-priced while canonical symbols are often *USDT.
        venue_ccy = "USD" if q.venue == "coinbase" and quote_ccy == "USDT" else quote_ccy
        if venue_ccy != "USD":
            bid, ask = self.basis.normalize_quote_prices(q.bid, q.ask, venue_ccy, "USD")
        else:
            bid, ask = q.bid, q.ask
        return Quote(
            venue=q.venue,
            symbol=q.symbol,
            bid=bid,
            ask=ask,
            bid_size=q.bid_size,
            ask_size=q.ask_size,
            exchange_ts=q.exchange_ts,
            received_ts=q.received_ts,
            sequence=q.sequence,
        )

    async def consume(self, adapter):
        async for q in adapter.stream():
            with self.telemetry.span("consume_quote", venue=q.venue, symbol=q.symbol):
                offset_ms = self.clock.observe(q.venue, q.exchange_ts, q.received_ts)
                nq = self._normalize_quote(q)
                self.quote_count += 1
                await self.state.update(nq)
                payload = nq.to_dict()
                payload["clock_offset_ms"] = offset_ms
                payload["quote_currency"] = "USD"
                await self.bus.publish({"type": "quote", "data": payload})
                asyncio.create_task(self._journal_quote(payload))
                await self.scan(nq.symbol)

    async def consume_book(self, adapter):
        async for update in adapter.stream():
            with self.telemetry.span(
                "consume_book",
                venue=update.venue,
                symbol=update.symbol,
                is_snapshot=update.is_snapshot,
            ):
                book = self.books.apply(update)
                event = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "venue": update.venue,
                    "symbol": update.symbol,
                    "first_update_id": update.first_update_id,
                    "final_update_id": update.final_update_id,
                    "is_snapshot": update.is_snapshot,
                    "status": book.status.value,
                    "gap_count": book.gap_count,
                    "top": book.top(5),
                }
                await self.bus.publish({"type": "book", "data": event})
                asyncio.create_task(self._journal_book(event))
                if book.needs_resnapshot() and hasattr(adapter, "request_snapshot"):
                    asyncio.create_task(adapter.request_snapshot(update.symbol))

    async def _journal_quote(self, payload: dict):
        try:
            await self.data_bus.publish(
                settings.kafka_quotes_topic,
                f"{payload.get('venue')}:{payload.get('symbol')}",
                payload,
            )
            await self.archive.write_tick(payload)
        except Exception:
            pass

    async def _journal_book(self, payload: dict):
        try:
            await self.data_bus.publish(
                settings.kafka_books_topic,
                f"{payload.get('venue')}:{payload.get('symbol')}",
                payload,
            )
            await self.archive.write_book(payload)
        except Exception:
            pass

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
        with self.telemetry.span("scan", symbol=symbol, execution_mode=settings.resolved_execution_mode()):
            quotes = await self.state.for_symbol(symbol)
            for op in self.arb.scan(quotes)[:2]:
                self.opportunity_count += 1
                self.opportunities.appendleft(op)
                d = op.to_dict()
                await self.bus.publish({"type": "opportunity", "data": d})
                asyncio.create_task(persist_opportunity(d))
                mode = settings.resolved_execution_mode()
                if mode == "live":
                    await self.bus.publish({
                        "type": "risk_decision",
                        "data": {
                            "opportunity_id": op.id,
                            "allowed": False,
                            "reason": self.live_broker_error or "live_trading_not_enabled",
                            "execution_mode": "live",
                        },
                    })
                    continue
                if not self.can_execute_route(op):
                    continue
                if mode == "shadow":
                    await self.shadow_execute(op)
                elif mode == "testnet":
                    if settings.testnet_auto_execute:
                        await self.testnet_execute(op)
                elif settings.paper_auto_execute:
                    await self.paper_execute(op)

            histories = {q.venue: await self.state.history(q.venue, symbol, 25) for q in quotes}
            for op in self.leadlag.scan(histories)[:1]:
                self.opportunities.appendleft(op)
                await self.bus.publish({"type": "analysis_opportunity", "data": op.to_dict()})

    async def testnet_execute(self, op):
        with self.telemetry.span("testnet_execute", opportunity_id=op.id, symbol=op.symbol):
            # Prefer fee-tier taker rates for cost-aware detection on subsequent scans.
            self.costs.venue_fee_bps = {
                **settings.fees,
                **{v: self.fee_schedule.taker_bps(v) for v in settings.testnet_venue_list},
            }
            portfolio = self.broker.snapshot(await self.marks())
            before = len(self.gateway.fills)
            result = await self.gateway.execute_arbitrage(
                op, portfolio, settings.paper_order_notional, strategy=self.arb.name
            )
            if not result.get("ok"):
                return
            new_fills = list(self.gateway.fills)[before:]
            for f in new_fills:
                # Mirror venue fills into the local portfolio ledger for P&L/UI.
                self.broker.apply_external_fill(
                    OrderRequest(
                        f.venue, f.symbol, f.side, f.quantity, f.price, f.strategy, f.opportunity_id,
                    ),
                    f.price,
                    f.fee,
                )
                self.fills.append(f)
                asyncio.create_task(persist_fill(f.to_dict()))
            self.trade_count = self.gateway.trade_count
            await self.bus.publish({
                "type": "portfolio",
                "data": asdict(self.broker.snapshot(await self.marks())),
            })

    async def shadow_execute(self, op):
        with self.telemetry.span("shadow_execute", opportunity_id=op.id, symbol=op.symbol):
            if self.native:
                result = await self.native.evaluate_arbitrage(
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
                        "execution_mode": "shadow",
                    },
                })
                if not result["allowed"]:
                    return
                await self._record_shadow_fills(op, result)
                return

            p = self.broker.snapshot(await self.marks())
            d = self.risk.evaluate(
                op, p, settings.paper_order_notional, settings.default_slippage_bps
            )
            await self.bus.publish({
                "type": "risk_decision",
                "data": {
                    "opportunity_id": op.id,
                    "allowed": d.allowed,
                    "reason": d.reason if not d.allowed else "shadow_approved",
                    "approved_notional": d.approved_notional,
                    "engine": "python",
                    "execution_mode": "shadow",
                },
            })
            if not d.allowed:
                return
            slip = settings.default_slippage_bps / 10000.0
            qty = d.approved_notional / (op.buy_price * (1 + slip))
            buy_exec = op.buy_price * (1 + slip)
            sell_exec = op.sell_price * (1 - slip)
            buy_fee = qty * buy_exec * settings.fees.get(op.buy_venue, 10) / 10000.0
            sell_fee = qty * sell_exec * settings.fees.get(op.sell_venue, 10) / 10000.0
            result = {
                "quantity": qty,
                "buy_exec_price": buy_exec,
                "sell_exec_price": sell_exec,
                "buy_fee": buy_fee,
                "sell_fee": sell_fee,
                "trade_pnl": (qty * sell_exec - qty * buy_exec) - buy_fee - sell_fee,
                "latency_ns": 0,
            }
            await self._record_shadow_fills(op, result)

    async def _record_shadow_fills(self, op, result):
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
            fd["shadow"] = True
            fd["engine_latency_ns"] = result.get("latency_ns", 0)
            fd["trade_pnl"] = result.get("trade_pnl", 0)
            self.shadow_fills.append(f)
            await self.bus.publish({"type": "shadow_fill", "data": fd})
        self.shadow_trade_count += 1

    async def paper_execute(self, op):
        with self.telemetry.span("paper_execute", opportunity_id=op.id, symbol=op.symbol):
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
                        "execution_mode": "paper",
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
                    "execution_mode": "paper",
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
        if settings.is_testnet:
            return asdict(self.broker.snapshot(await self.marks()))
        if self.native and self.native_identity:
            return await self.native.snapshot()
        return asdict(self.broker.snapshot(await self.marks()))

    async def risk_snapshot(self):
        if settings.is_testnet or not (self.native and self.native_identity):
            return {"halted": self.risk.halted, "rejections": self.risk.rejections}
        s = await self.native.snapshot()
        return {"halted": s["halted"], "rejections": s["rejection_count"]}

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
            "market_mode": settings.resolved_market_mode(),
            "execution_mode": settings.resolved_execution_mode(),
            "paper_trading": settings.resolved_execution_mode() == "paper",
            "shadow_trading": settings.is_shadow,
            "testnet_trading": settings.is_testnet,
            "execution_engine": (
                "testnet-gateway" if settings.is_testnet else (self.native_identity or "python")
            ),
            "execution_transport": (
                "authenticated-testnet" if settings.is_testnet
                else ("tcp-native" if self.native and self.native_identity else "in-process")
            ),
            "execution": {
                "engine": (
                    "testnet-gateway" if settings.is_testnet else (self.native_identity or "python")
                ),
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
                "shadow_trades": self.shadow_trade_count,
                "hedges": self.gateway.hedge_count,
                "open_orders": len(self.gateway.fsm.open_orders()),
            },
            "risk": risk,
            "portfolio": portfolio,
            "quotes": [q.to_dict() for q in await self.state.all_quotes()],
            "opportunities": [o.to_dict() for o in list(self.opportunities)[:50]],
            "fills": [f.to_dict() for f in list(self.fills)[-50:]][::-1],
            "shadow_fills": [f.to_dict() for f in list(self.shadow_fills)[-50:]][::-1],
            "basis": self.basis.to_dict(),
            "clock": self.clock.snapshot(),
            "orderbooks": self.books.snapshot(),
            "data_plane": {
                "enabled": settings.data_plane_enabled,
                "bus": self.data_bus.stats(),
                "archive": self.archive.stats(),
                "telemetry": self.telemetry.stats(),
            },
            "execution_plane": self.gateway.snapshot() if settings.is_testnet else {
                "enabled": False,
                "mode": settings.resolved_execution_mode(),
                "live_error": self.live_broker_error,
            },
            "instruments": self.registry.to_list(),
        }


runtime = QuantRuntime()
