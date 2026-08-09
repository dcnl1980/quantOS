import asyncio
import json
from typing import Any

class NativeExecutionUnavailable(RuntimeError):
    pass

class NativeExecutionClient:
    """
    Persistent private TCP client for the C++20 and Rust execution services.
    Calls are serialized on one connection. A broken connection is recreated once.
    """
    def __init__(self, host: str, port: int, timeout_ms: int = 1000):
        self.host = host
        self.port = port
        self.timeout = timeout_ms / 1000
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.lock = asyncio.Lock()

    async def connect(self):
        if self.writer and not self.writer.is_closing():
            return
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.timeout
        )

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None

    async def _request(self, line: str) -> dict[str, Any]:
        async with self.lock:
            for attempt in range(2):
                try:
                    await self.connect()
                    assert self.writer is not None and self.reader is not None
                    self.writer.write((line + "\n").encode())
                    await asyncio.wait_for(self.writer.drain(), self.timeout)
                    raw = await asyncio.wait_for(self.reader.readline(), self.timeout)
                    if not raw:
                        raise ConnectionError("execution engine closed connection")
                    obj = json.loads(raw)
                    if obj.get("type") == "error":
                        raise RuntimeError(obj.get("error", "native engine error"))
                    return obj
                except Exception as e:
                    await self.close()
                    if attempt:
                        raise NativeExecutionUnavailable(
                            f"native execution engine unavailable at {self.host}:{self.port}: {e}"
                        ) from e
            raise NativeExecutionUnavailable("native execution engine request failed")

    async def ping(self):
        return await self._request("PING")

    async def snapshot(self):
        return await self._request("SNAPSHOT")

    async def reset(self):
        return await self._request("RESET")

    async def reset_circuit_breaker(self):
        return await self._request("RESET_CB")

    def _arb_line(
        self,
        command: str,
        opportunity,
        desired_notional: float,
        fees: dict[str, float],
        slippage_bps: float,
    ) -> str:
        clean = lambda s: str(s).replace("|", "_").replace("\n", "_")
        fields = [
            command,
            clean(opportunity.id),
            clean(opportunity.symbol),
            clean(opportunity.buy_venue),
            clean(opportunity.sell_venue),
            f"{opportunity.buy_price:.12f}",
            f"{opportunity.sell_price:.12f}",
            f"{opportunity.net_edge_bps:.12f}",
            f"{opportunity.max_notional:.12f}",
            f"{desired_notional:.12f}",
            f"{fees.get(opportunity.buy_venue, 10.0):.12f}",
            f"{fees.get(opportunity.sell_venue, 10.0):.12f}",
            f"{slippage_bps:.12f}",
        ]
        return "|".join(fields)

    async def execute_arbitrage(
        self,
        opportunity,
        desired_notional: float,
        fees: dict[str, float],
        slippage_bps: float,
    ):
        return await self._request(
            self._arb_line("EXEC_ARB", opportunity, desired_notional, fees, slippage_bps)
        )

    async def evaluate_arbitrage(
        self,
        opportunity,
        desired_notional: float,
        fees: dict[str, float],
        slippage_bps: float,
    ):
        return await self._request(
            self._arb_line("EVAL_ARB", opportunity, desired_notional, fees, slippage_bps)
        )
