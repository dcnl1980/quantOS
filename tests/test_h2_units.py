import asyncio

import pytest

from quant_os.models import Side, Opportunity, OpportunityType, PortfolioSnapshot
from quant_os.orders import Order, OrderState, OrderStateMachine, OrderTransitionError
from quant_os.fee_tiers import FeeSchedule
from quant_os.inventory import InventoryAllocator
from quant_os.hedge import PartialFillHedgePolicy, HedgeAction
from quant_os.reconciliation import Reconciler, VenueOrderReport
from quant_os.venues import SimulatedTestnetBroker
from quant_os.live_broker import LiveBroker, LiveTradingDisabled
from quant_os.risk import RiskEngine, RiskConfig


def test_order_fsm_idempotent_create_and_fill():
    fsm = OrderStateMachine()
    o = Order("sim_a", "BTCUSDT", Side.BUY, 1.0, 100.0, "arb", client_order_id="c1")
    assert fsm.register(o).client_order_id == "c1"
    assert fsm.register(o).state == OrderState.NEW  # idempotent
    fsm.accept("c1", "v1")
    fsm.apply_fill("c1", 0.4, 100.1, 0.01)
    assert fsm.get("c1").state == OrderState.PARTIALLY_FILLED
    fsm.apply_fill("c1", 0.6, 100.2, 0.01)
    assert fsm.get("c1").state == OrderState.FILLED
    assert abs(fsm.get("c1").filled_qty - 1.0) < 1e-9


def test_order_fsm_cancel_replace_transitions():
    fsm = OrderStateMachine()
    o = Order("sim_a", "ETHUSDT", Side.SELL, 2.0, 50.0, "arb", client_order_id="c2")
    fsm.register(o)
    fsm.accept("c2", "v2")
    fsm.request_cancel("c2")
    fsm.confirm_cancel("c2")
    assert fsm.get("c2").state == OrderState.CANCELLED

    o3 = Order("sim_a", "ETHUSDT", Side.BUY, 1.0, 49.0, "arb", client_order_id="c3")
    fsm.register(o3)
    fsm.accept("c3", "v3")
    repl = Order("sim_a", "ETHUSDT", Side.BUY, 1.0, 48.5, "arb")
    fsm.request_replace("c3", repl)
    fsm.accept(repl.client_order_id, "v4")
    fsm.confirm_replace("c3")
    assert fsm.get("c3").state == OrderState.REPLACED
    with pytest.raises(OrderTransitionError):
        fsm.apply_fill("c3", 0.1, 48.5)


def test_fee_tiers_and_inventory():
    fees = FeeSchedule.default()
    fees.set_volume("binance", 6_000_000)
    assert fees.tier_for("binance").name == "vip2"
    assert fees.taker_bps("binance") == 9.0

    inv = InventoryAllocator(100000, {"sim_a": 0.5, "sim_b": 0.5})
    assert abs(inv.allocate("sim_a", 10000) - 10000) < 1e-9
    assert inv.available("sim_a") == 40000
    inv.apply_fill("sim_a", "BTCUSDT", 0.1, 10000)
    assert abs(inv.position("sim_a", "BTCUSDT") - 0.1) < 1e-9
    assert abs(inv.available("sim_a") - 50000) < 1e-6


def test_partial_fill_hedge_policy():
    policy = PartialFillHedgePolicy()
    buy = Order("a", "X", Side.BUY, 1.0, 100, "arb", client_order_id="b")
    sell = Order("b", "X", Side.SELL, 1.0, 101, "arb", client_order_id="s")
    buy.state = OrderState.PARTIALLY_FILLED
    sell.state = OrderState.PARTIALLY_FILLED
    buy.filled_qty = 0.6
    sell.filled_qty = 0.6
    d = policy.evaluate(buy, sell)
    assert d.action == HedgeAction.CANCEL_BOTH

    buy.filled_qty = 0.9
    sell.filled_qty = 0.4
    sell.state = OrderState.FILLED
    sell.quantity = 0.4
    d2 = policy.evaluate(buy, sell)
    assert d2.action == HedgeAction.HEDGE_RESIDUAL
    assert d2.target_side == "sell"


def test_reconciler_repairs_fill_gap():
    fsm = OrderStateMachine()
    o = Order("sim_a", "BTCUSDT", Side.BUY, 1.0, 100, "arb", client_order_id="r1")
    fsm.register(o)
    fsm.accept("r1", "vr1")
    fsm.apply_fill("r1", 0.2, 100.0, 0.0)
    recon = Reconciler(fsm, auto_repair=True)
    result = recon.reconcile([
        VenueOrderReport("r1", "vr1", "partially_filled", 0.5, 100.0, 0.01)
    ])
    assert result["critical"] >= 1
    assert abs(fsm.get("r1").filled_qty - 0.5) < 1e-9


@pytest.mark.asyncio
async def test_simulated_testnet_idempotent_place_cancel():
    broker = SimulatedTestnetBroker("sim_a", partial_fill_ratio=0.5)
    await broker.connect()
    order = Order("sim_a", "BTCUSDT", Side.BUY, 1.0, 100.0, "arb", client_order_id="idemp1")
    r1 = await broker.place(order)
    r2 = await broker.place(order)
    assert r1.ok and r2.ok and r1.venue_order_id == r2.venue_order_id
    assert r1.fill_qty == 0.5
    c = await broker.cancel(order)
    assert c.ok
    reports = await broker.open_orders()
    assert reports[0].state == "cancelled"
    await broker.close()


def test_live_broker_still_gated():
    with pytest.raises(LiveTradingDisabled):
        LiveBroker(False, "")
    with pytest.raises(LiveTradingDisabled):
        LiveBroker(True, LiveBroker.ACK, testnet_validated=False)
    with pytest.raises(NotImplementedError):
        LiveBroker(True, LiveBroker.ACK, testnet_validated=True)


@pytest.mark.asyncio
async def test_gateway_paired_testnet_trade():
    from app.execution.gateway import ExecutionGateway

    events = []

    async def publish(msg):
        events.append(msg)

    risk = RiskEngine(RiskConfig(max_order_notional=2500, min_net_edge_bps=8))
    fees = FeeSchedule.default()
    inv = InventoryAllocator(100000, {"sim_a": 0.5, "sim_b": 0.5})
    gw = ExecutionGateway(risk, fees, inv, publish, partial_fill_ratio=0.65)
    await gw.start(["sim_a", "sim_b"], "testnet", "testnet")
    try:
        op = Opportunity(
            "BTCUSDT", OpportunityType.CROSS_VENUE, "sim_a", "sim_b",
            100, 101.5, 150, 50, 0.9, 10000,
        )
        portfolio = PortfolioSnapshot(100000, 100000, 0, 0, 100000, 0, {}, {})
        result = await gw.execute_arbitrage(op, portfolio, 1000)
        assert result["ok"]
        assert gw.trade_count >= 1
        assert gw.hedge_count >= 1
        assert any(e["type"] == "execution_session" for e in events)
        recon = await gw.reconcile_once()
        assert "mismatch_count" in recon
    finally:
        await gw.stop()
