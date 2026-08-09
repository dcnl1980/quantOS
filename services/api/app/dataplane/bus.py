"""Non-blocking market-data bus (in-memory or Kafka/Redpanda)."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, Protocol

log = logging.getLogger("quant.dataplane.bus")


class EventBusProducer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None: ...
    def stats(self) -> dict[str, Any]: ...


class MemoryBus:
    def __init__(self, maxlen: int = 10_000):
        self.topics: dict[str, deque[dict[str, Any]]] = {}
        self.maxlen = maxlen
        self.published = 0
        self.dropped = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            q = self.topics.setdefault(topic, deque(maxlen=self.maxlen))
            if len(q) == self.maxlen:
                self.dropped += 1
            q.append({"key": key, "payload": payload})
            self.published += 1

    def read(self, topic: str, limit: int = 100) -> list[dict[str, Any]]:
        q = self.topics.get(topic, deque())
        return list(q)[-limit:]

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "memory",
            "published": self.published,
            "dropped": self.dropped,
            "topics": {k: len(v) for k, v in self.topics.items()},
        }


class KafkaBus:
    """Optional aiokafka producer. Fail-open: never blocks the market loop."""

    def __init__(self, bootstrap: str, client_id: str = "quant-os-api"):
        self.bootstrap = bootstrap
        self.client_id = client_id
        self.producer = None
        self.published = 0
        self.errors = 0
        self._fallback = MemoryBus()

    async def start(self) -> None:
        try:
            from aiokafka import AIOKafkaProducer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap,
                client_id=self.client_id,
                acks=1,
                linger_ms=5,
            )
            await self.producer.start()
            log.info("kafka producer started: %s", self.bootstrap)
        except Exception as exc:
            log.warning("kafka unavailable, using memory bus: %s", exc)
            self.producer = None
            await self._fallback.start()

    async def stop(self) -> None:
        if self.producer is not None:
            try:
                await self.producer.stop()
            except Exception:
                pass
        await self._fallback.stop()

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode()
        if self.producer is None:
            await self._fallback.publish(topic, key, payload)
            return
        try:
            await self.producer.send_and_wait(topic, body, key=key.encode())
            self.published += 1
        except Exception as exc:
            self.errors += 1
            log.debug("kafka publish failed: %s", exc)
            await self._fallback.publish(topic, key, payload)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "kafka" if self.producer is not None else "kafka+memory-fallback",
            "bootstrap": self.bootstrap,
            "published": self.published + self._fallback.published,
            "errors": self.errors,
            "fallback": self._fallback.stats(),
        }


def build_bus(enabled: bool, backend: str, bootstrap: str) -> EventBusProducer:
    if not enabled:
        return MemoryBus()
    if backend.lower() in {"kafka", "redpanda"}:
        return KafkaBus(bootstrap)
    return MemoryBus()
