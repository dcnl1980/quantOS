"""Binance partial depth stream with REST snapshot reseeding for gap recovery."""
from __future__ import annotations

import asyncio
import json
import logging
from urllib import error, request

import websockets

from quant_os.orderbook import BookUpdate

log = logging.getLogger("quant.adapters.binance_depth")


class BinanceDepthAdapter:
    WS = "wss://stream.binance.com:9443/stream?streams="
    REST = "https://api.binance.com/api/v3/depth"

    def __init__(self, symbols: list[str], depth: int = 20):
        self.symbols = [s.upper() for s in symbols]
        self.depth = 5 if depth <= 5 else 10 if depth <= 10 else 20
        self._snapshot_requests: asyncio.Queue[str] = asyncio.Queue()

    async def request_snapshot(self, symbol: str):
        await self._snapshot_requests.put(symbol.upper())

    async def stream(self):
        streams = "/".join(f"{s.lower()}@depth{self.depth}@100ms" for s in self.symbols)
        url = self.WS + streams
        backoff = 1
        while True:
            try:
                for symbol in self.symbols:
                    snap = await asyncio.to_thread(self._fetch_snapshot, symbol)
                    if snap:
                        yield snap
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_queue=4096) as ws:
                    backoff = 1
                    while True:
                        while not self._snapshot_requests.empty():
                            symbol = self._snapshot_requests.get_nowait()
                            snap = await asyncio.to_thread(self._fetch_snapshot, symbol)
                            if snap:
                                yield snap
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=0.05)
                        except asyncio.TimeoutError:
                            continue
                        msg = json.loads(raw)
                        data = msg.get("data", msg)
                        if not {"s", "U", "u", "b", "a"}.issubset(data):
                            continue
                        yield BookUpdate(
                            venue="binance",
                            symbol=str(data["s"]).upper(),
                            first_update_id=int(data["U"]),
                            final_update_id=int(data["u"]),
                            bids=[(float(p), float(q)) for p, q in data.get("b", [])],
                            asks=[(float(p), float(q)) for p, q in data.get("a", [])],
                            is_snapshot=False,
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("binance depth reconnect: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _fetch_snapshot(self, symbol: str) -> BookUpdate | None:
        try:
            req = request.Request(
                f"{self.REST}?symbol={symbol.upper()}&limit={self.depth}",
                headers={"User-Agent": "quant-os/1.0"},
            )
            with request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
            return BookUpdate(
                venue="binance",
                symbol=symbol.upper(),
                first_update_id=int(data["lastUpdateId"]),
                final_update_id=int(data["lastUpdateId"]),
                bids=[(float(p), float(q)) for p, q in data.get("bids", [])],
                asks=[(float(p), float(q)) for p, q in data.get("asks", [])],
                is_snapshot=True,
            )
        except (error.URLError, TimeoutError, ValueError, KeyError) as exc:
            log.debug("binance snapshot failed for %s: %s", symbol, exc)
            return None
