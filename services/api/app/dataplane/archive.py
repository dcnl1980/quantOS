"""Raw tick archive (in-memory or ClickHouse HTTP)."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, Protocol
from urllib import error, request

log = logging.getLogger("quant.dataplane.archive")


class TickArchive(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def write_tick(self, tick: dict[str, Any]) -> None: ...
    async def write_book(self, book_event: dict[str, Any]) -> None: ...
    def stats(self) -> dict[str, Any]: ...
    def recent_ticks(self, limit: int = 50) -> list[dict[str, Any]]: ...


class MemoryArchive:
    def __init__(self, maxlen: int = 20_000):
        self.ticks: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.books: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.written = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def write_tick(self, tick: dict[str, Any]) -> None:
        async with self._lock:
            self.ticks.append(tick)
            self.written += 1

    async def write_book(self, book_event: dict[str, Any]) -> None:
        async with self._lock:
            self.books.append(book_event)
            self.written += 1

    def recent_ticks(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.ticks)[-limit:]

    def recent_books(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.books)[-limit:]

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "memory",
            "written": self.written,
            "ticks": len(self.ticks),
            "books": len(self.books),
        }


class ClickHouseArchive:
    """Best-effort ClickHouse archive via HTTP. Falls back to memory on failure."""

    def __init__(self, url: str, database: str = "quant", user: str = "default", password: str = ""):
        self.url = url.rstrip("/")
        self.database = database
        self.user = user
        self.password = password
        self.fallback = MemoryArchive()
        self.written = 0
        self.errors = 0
        self.ready = False

    async def start(self) -> None:
        ddl_ticks = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.ticks (
            ts DateTime64(3, 'UTC'),
            venue String,
            symbol String,
            bid Float64,
            ask Float64,
            bid_size Float64,
            ask_size Float64,
            sequence Nullable(Int64),
            payload String
        ) ENGINE = MergeTree ORDER BY (symbol, venue, ts)
        """
        ddl_books = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.book_updates (
            ts DateTime64(3, 'UTC'),
            venue String,
            symbol String,
            first_update_id Int64,
            final_update_id Int64,
            is_snapshot UInt8,
            payload String
        ) ENGINE = MergeTree ORDER BY (symbol, venue, ts)
        """
        ok = await asyncio.to_thread(self._exec, f"CREATE DATABASE IF NOT EXISTS {self.database}")
        ok = ok and await asyncio.to_thread(self._exec, ddl_ticks)
        ok = ok and await asyncio.to_thread(self._exec, ddl_books)
        self.ready = ok
        if not ok:
            log.warning("clickhouse unavailable, using memory archive at %s", self.url)
        await self.fallback.start()

    async def stop(self) -> None:
        await self.fallback.stop()

    async def write_tick(self, tick: dict[str, Any]) -> None:
        await self.fallback.write_tick(tick)
        if not self.ready:
            return
        row = {
            "ts": tick.get("received_ts") or tick.get("exchange_ts"),
            "venue": tick.get("venue"),
            "symbol": tick.get("symbol"),
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "bid_size": tick.get("bid_size", 0),
            "ask_size": tick.get("ask_size", 0),
            "sequence": tick.get("sequence"),
            "payload": json.dumps(tick, default=str),
        }
        sql = (
            f"INSERT INTO {self.database}.ticks FORMAT JSONEachRow\n"
            + json.dumps(row, default=str)
        )
        if not await asyncio.to_thread(self._exec, sql):
            self.errors += 1
        else:
            self.written += 1

    async def write_book(self, book_event: dict[str, Any]) -> None:
        await self.fallback.write_book(book_event)
        if not self.ready:
            return
        row = {
            "ts": book_event.get("ts"),
            "venue": book_event.get("venue"),
            "symbol": book_event.get("symbol"),
            "first_update_id": book_event.get("first_update_id", 0),
            "final_update_id": book_event.get("final_update_id", 0),
            "is_snapshot": 1 if book_event.get("is_snapshot") else 0,
            "payload": json.dumps(book_event, default=str),
        }
        sql = (
            f"INSERT INTO {self.database}.book_updates FORMAT JSONEachRow\n"
            + json.dumps(row, default=str)
        )
        if not await asyncio.to_thread(self._exec, sql):
            self.errors += 1
        else:
            self.written += 1

    def recent_ticks(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.fallback.recent_ticks(limit)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "clickhouse" if self.ready else "clickhouse+memory-fallback",
            "url": self.url,
            "written": self.written,
            "errors": self.errors,
            "fallback": self.fallback.stats(),
        }

    def _exec(self, sql: str) -> bool:
        try:
            auth = f"?user={self.user}"
            if self.password:
                auth += f"&password={self.password}"
            req = request.Request(
                f"{self.url}/{auth}",
                data=sql.encode(),
                method="POST",
                headers={"Content-Type": "text/plain"},
            )
            with request.urlopen(req, timeout=2.0) as resp:
                return 200 <= resp.status < 300
        except (error.URLError, TimeoutError, ValueError) as exc:
            log.debug("clickhouse exec failed: %s", exc)
            return False


def build_archive(enabled: bool, backend: str, url: str, database: str) -> TickArchive:
    if not enabled:
        return MemoryArchive()
    if backend.lower() in {"clickhouse", "ch"}:
        return ClickHouseArchive(url=url, database=database)
    return MemoryArchive()
