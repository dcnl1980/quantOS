from datetime import datetime, timezone, timedelta

from quant_os.orderbook import OrderBook, BookUpdate, BookStatus
from quant_os.instrument_registry import InstrumentRegistry
from quant_os.basis import BasisModel
from quant_os.clock_telemetry import ClockTelemetry


def test_orderbook_snapshot_and_live_update():
    book = OrderBook("binance", "BTCUSDT")
    book.apply_update(BookUpdate(
        "binance", "BTCUSDT", 100, 100,
        bids=[(100.0, 1.5), (99.0, 2.0)],
        asks=[(101.0, 1.0), (102.0, 3.0)],
        is_snapshot=True,
    ))
    assert book.status in {BookStatus.SYNCING, BookStatus.LIVE}
    assert book.best_bid().price == 100.0
    assert book.best_ask().price == 101.0

    status = book.apply_update(BookUpdate(
        "binance", "BTCUSDT", 101, 101,
        bids=[(100.0, 0.0), (100.5, 1.0)],
        asks=[(101.0, 2.0)],
    ))
    assert status == BookStatus.LIVE
    assert book.best_bid().price == 100.5
    assert 100.0 not in book.bids


def test_orderbook_gap_detection_and_resnapshot():
    book = OrderBook("binance", "BTCUSDT")
    book.apply_update(BookUpdate(
        "binance", "BTCUSDT", 10, 10,
        bids=[(100.0, 1.0)], asks=[(101.0, 1.0)], is_snapshot=True,
    ))
    status = book.apply_update(BookUpdate(
        "binance", "BTCUSDT", 20, 25,
        bids=[(100.0, 2.0)], asks=[(101.0, 2.0)],
    ))
    assert status == BookStatus.GAP
    assert book.needs_resnapshot()
    assert book.gap_count == 1

    book.apply_update(BookUpdate(
        "binance", "BTCUSDT", 30, 30,
        bids=[(100.0, 3.0)], asks=[(101.0, 3.0)], is_snapshot=True,
    ))
    assert book.last_update_id == 30
    assert book.best_bid().size == 3.0


def test_instrument_registry_default_graph():
    reg = InstrumentRegistry.default(["BTCUSDT", "ETHUSDT"])
    assert reg.get("BTCUSDT").base == "BTC"
    assert reg.listing("coinbase", "BTCUSDT").venue_symbol == "BTC-USD"
    graph = reg.graph()
    assert any(e["type"] == "PRICED_IN" for e in graph["edges"])
    assert any(n["type"] == "underlying" for n in graph["nodes"])


def test_usdt_usd_basis_conversion():
    basis = BasisModel(usdt_usd=0.999)
    bid, ask = basis.normalize_quote_prices(100.0, 100.2, "USDT", "USD")
    assert abs(bid - 99.9) < 1e-9
    assert abs(ask - 100.0998) < 1e-6
    assert basis.basis_bps() == -10.0


def test_clock_telemetry_offset():
    clock = ClockTelemetry(stale_ms=50)
    exchange = datetime.now(timezone.utc) - timedelta(milliseconds=120)
    received = datetime.now(timezone.utc)
    offset = clock.observe("binance", exchange, received)
    assert offset > 100
    snap = clock.snapshot()
    assert snap["venues"][0]["stale"] is True
