"""End-to-end: simulator -> H1 data plane -> shadow (no orders) and paper paths."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "quant"))
sys.path.insert(0, str(ROOT / "services" / "api"))

# Force deterministic offline settings before importing app modules.
os.environ.setdefault("EXECUTION_ENGINE", "python")
os.environ.setdefault("DATA_PLANE_ENABLED", "true")
os.environ.setdefault("BUS_BACKEND", "memory")
os.environ.setdefault("ARCHIVE_BACKEND", "memory")
os.environ.setdefault("OTEL_ENABLED", "true")
os.environ.setdefault("ENABLE_L2_BOOKS", "false")
os.environ.setdefault("MARKET_MODE", "simulator")
os.environ.setdefault("EXECUTION_MODE", "paper")

from app.config import settings  # noqa: E402
from app.runtime import QuantRuntime  # noqa: E402
from quant_os.models import Quote  # noqa: E402
from quant_os.orderbook import BookUpdate  # noqa: E402


def _configure(**kwargs):
    for key, value in kwargs.items():
        setattr(settings, key, value)


@pytest.mark.asyncio
async def test_e2e_shadow_mode_no_portfolio_mutation():
    _configure(
        market_mode="simulator",
        execution_mode="shadow",
        execution_engine="python",
        paper_auto_execute=True,
        sim_tick_ms=40,
        sim_arbitrage_probability=0.55,
        data_plane_enabled=True,
        bus_backend="memory",
        archive_backend="memory",
        otel_enabled=True,
        enable_l2_books=False,
        min_execution_interval_ms=50,
    )
    rt = QuantRuntime()
    await rt.start()
    try:
        deadline = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < deadline:
            if rt.shadow_trade_count >= 1 and rt.quote_count >= 10:
                break
            await asyncio.sleep(0.1)
        snap = await rt.snapshot()
        assert snap["execution_mode"] == "shadow"
        assert snap["market_mode"] == "simulator"
        assert snap["stats"]["quotes"] >= 10
        assert snap["stats"]["shadow_trades"] >= 1
        assert snap["stats"]["trades"] == 0
        assert abs(snap["portfolio"]["equity"] - settings.initial_cash) < 1e-6
        assert len(snap["shadow_fills"]) >= 2
        assert snap["data_plane"]["bus"]["published"] >= 10
        assert snap["data_plane"]["archive"]["written"] >= 10
        assert snap["data_plane"]["telemetry"]["spans"] >= 1
        assert snap["clock"]["samples"] >= 1
        assert "BTCUSDT" in {i["symbol"] for i in snap["instruments"]}
    finally:
        await rt.stop()


@pytest.mark.asyncio
async def test_e2e_paper_mode_still_executes():
    _configure(
        market_mode="simulator",
        execution_mode="paper",
        execution_engine="python",
        paper_auto_execute=True,
        sim_tick_ms=40,
        sim_arbitrage_probability=0.55,
        data_plane_enabled=True,
        bus_backend="memory",
        archive_backend="memory",
        enable_l2_books=False,
        min_execution_interval_ms=50,
        initial_cash=100000,
    )
    rt = QuantRuntime()
    # Fresh broker cash after settings change
    rt.broker.cash = settings.initial_cash
    await rt.start()
    try:
        deadline = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < deadline:
            if rt.trade_count >= 1:
                break
            await asyncio.sleep(0.1)
        snap = await rt.snapshot()
        assert snap["execution_mode"] == "paper"
        assert snap["stats"]["trades"] >= 1
        assert snap["stats"]["shadow_trades"] == 0
        assert abs(snap["portfolio"]["equity"] - settings.initial_cash) > 1e-6 or snap["portfolio"]["realized_pnl"] != 0
    finally:
        await rt.stop()


@pytest.mark.asyncio
async def test_e2e_market_mode_shadow_alias():
    _configure(
        market_mode="shadow",
        execution_mode="paper",  # alias should force shadow execution
        execution_engine="python",
        enable_l2_books=False,
    )
    assert settings.resolved_market_mode() == "live"
    assert settings.resolved_execution_mode() == "shadow"


@pytest.mark.asyncio
async def test_e2e_l2_gap_recovery_and_journal():
    _configure(
        market_mode="simulator",
        execution_mode="shadow",
        execution_engine="python",
        data_plane_enabled=True,
        bus_backend="memory",
        archive_backend="memory",
        enable_l2_books=True,
    )
    rt = QuantRuntime()
    await rt.data_bus.start()
    await rt.archive.start()
    try:
        snap = BookUpdate(
            venue="binance", symbol="BTCUSDT",
            first_update_id=100, final_update_id=100,
            bids=[(100.0, 1.0)], asks=[(101.0, 1.0)], is_snapshot=True,
        )
        gap = BookUpdate(
            venue="binance", symbol="BTCUSDT",
            first_update_id=150, final_update_id=160,
            bids=[(100.0, 2.0)], asks=[(101.0, 2.0)],
        )
        repair = BookUpdate(
            venue="binance", symbol="BTCUSDT",
            first_update_id=200, final_update_id=200,
            bids=[(100.5, 3.0)], asks=[(101.5, 3.0)], is_snapshot=True,
        )
        for update in (snap, gap, repair):
            book = rt.books.apply(update)
            event = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "venue": update.venue,
                "symbol": update.symbol,
                "first_update_id": update.first_update_id,
                "final_update_id": update.final_update_id,
                "is_snapshot": update.is_snapshot,
                "status": book.status.value,
                "gap_count": book.gap_count,
            }
            await rt._journal_book(event)

        books = rt.books.snapshot()
        assert books and books[0]["status"] in {"live", "syncing"}
        assert books[0]["gap_count"] >= 1
        assert rt.archive.stats()["books"] >= 3
        assert rt.data_bus.stats()["published"] >= 3
    finally:
        await rt.archive.stop()
        await rt.data_bus.stop()


@pytest.mark.asyncio
async def test_e2e_basis_normalization_on_consume():
    _configure(
        market_mode="simulator",
        execution_mode="shadow",
        execution_engine="python",
        usdt_usd_basis=0.99,
        data_plane_enabled=True,
        bus_backend="memory",
        archive_backend="memory",
        enable_l2_books=False,
    )
    rt = QuantRuntime()
    rt.basis.set_usdt_usd(0.99, source="test")

    class OneShot:
        async def stream(self):
            now = datetime.now(timezone.utc)
            yield Quote("binance", "BTCUSDT", 100.0, 100.2, 1, 1, now, now, 1)

    await rt.data_bus.start()
    await rt.archive.start()
    try:
        await rt.consume(OneShot())
        quotes = await rt.state.all_quotes()
        assert len(quotes) == 1
        assert abs(quotes[0].bid - 99.0) < 1e-9
        assert abs(quotes[0].ask - 99.198) < 1e-6
        assert rt.quote_count == 1
        assert rt.archive.stats()["ticks"] >= 1
    finally:
        await rt.archive.stop()
        await rt.data_bus.stop()
