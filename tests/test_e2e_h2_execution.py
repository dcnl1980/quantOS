"""End-to-end H2 testnet execution through QuantRuntime."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "quant"))
sys.path.insert(0, str(ROOT / "services" / "api"))

os.environ.setdefault("EXECUTION_ENGINE", "python")
os.environ.setdefault("MARKET_MODE", "simulator")
os.environ.setdefault("EXECUTION_MODE", "testnet")
os.environ.setdefault("DATA_PLANE_ENABLED", "true")
os.environ.setdefault("BUS_BACKEND", "memory")
os.environ.setdefault("ARCHIVE_BACKEND", "memory")
os.environ.setdefault("OTEL_ENABLED", "true")
os.environ.setdefault("ENABLE_L2_BOOKS", "false")

from app.config import settings  # noqa: E402
from app.runtime import QuantRuntime  # noqa: E402


def _configure(**kwargs):
    for key, value in kwargs.items():
        setattr(settings, key, value)


@pytest.mark.asyncio
async def test_e2e_testnet_execution_orders_and_recon():
    _configure(
        market_mode="simulator",
        execution_mode="testnet",
        execution_engine="python",
        testnet_venues="sim_a,sim_b",
        testnet_api_key="testnet",
        testnet_api_secret="testnet",
        testnet_auto_execute=True,
        testnet_partial_fill_ratio=0.65,
        paper_auto_execute=False,
        sim_tick_ms=40,
        sim_arbitrage_probability=0.6,
        data_plane_enabled=True,
        bus_backend="memory",
        archive_backend="memory",
        enable_l2_books=False,
        min_execution_interval_ms=40,
        initial_cash=100000,
        inventory_venue_weights="sim_a:0.5,sim_b:0.5",
    )
    rt = QuantRuntime()
    rt.broker.cash = settings.initial_cash
    await rt.start()
    try:
        deadline = asyncio.get_event_loop().time() + 10
        while asyncio.get_event_loop().time() < deadline:
            if rt.gateway.trade_count >= 1 and rt.quote_count >= 8:
                break
            await asyncio.sleep(0.1)
        snap = await rt.snapshot()
        assert snap["execution_mode"] == "testnet"
        assert snap["testnet_trading"] is True
        assert snap["stats"]["trades"] >= 1
        assert snap["stats"]["hedges"] >= 1
        assert snap["execution_plane"]["orders"]["orders"] >= 2
        assert len(snap["fills"]) >= 2
        # Portfolio should move after mirrored venue fills.
        assert abs(snap["portfolio"]["equity"] - settings.initial_cash) > 1e-6 or snap["portfolio"]["realized_pnl"] != 0
        recon = await rt.gateway.reconcile_once()
        assert "mismatch_count" in recon
        assert "sim_a" in snap["execution_plane"]["inventory"]["available"]
        assert snap["execution_plane"]["fees"]["tiers"]["sim_a"]["taker_bps"] == 5.0

        # Cancel/replace API surface on an open or recent order if any residual exists.
        open_orders = rt.gateway.fsm.open_orders()
        if open_orders:
            cid = open_orders[0].client_order_id
            cancelled = await rt.gateway.cancel_order(cid)
            assert "ok" in cancelled
        else:
            # Replace path still exercised via unit tests; here ensure endpoint objects exist.
            assert rt.gateway.fsm.snapshot()["orders"] >= 2
    finally:
        await rt.stop()


@pytest.mark.asyncio
async def test_e2e_live_mode_blocked():
    _configure(
        market_mode="simulator",
        execution_mode="live",
        execution_engine="python",
        enable_live_trading=False,
        live_trading_ack="",
        enable_l2_books=False,
        sim_tick_ms=40,
        sim_arbitrage_probability=0.8,
        min_execution_interval_ms=40,
        testnet_auto_execute=False,
        paper_auto_execute=False,
    )
    rt = QuantRuntime()
    await rt.start()
    try:
        assert rt.live_broker_error is not None
        # Inject one opportunity scan cycle via quotes from a short wait.
        await asyncio.sleep(0.5)
        snap = await rt.snapshot()
        assert snap["execution_mode"] == "live"
        assert snap["stats"]["trades"] == 0
        assert snap["execution_plane"]["enabled"] is False
    finally:
        await rt.stop()
