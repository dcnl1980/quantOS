"""OpenTelemetry setup with an in-memory fallback exporter for tests."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

log = logging.getLogger("quant.dataplane.telemetry")


@dataclass
class SpanRecord:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


class Telemetry:
    def __init__(self, enabled: bool = True, service_name: str = "quant-os-api"):
        self.enabled = enabled
        self.service_name = service_name
        self.spans: list[SpanRecord] = []
        self._tracer = None
        self._provider = None
        if enabled:
            self._init_otel()

    def _init_otel(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

            resource = Resource.create({"service.name": self.service_name})
            provider = TracerProvider(resource=resource)
            # Keep console quiet in product path; spans are captured via wrapper attributes.
            provider.add_span_processor(SimpleSpanProcessor(_RecordingExporter(self)))
            trace.set_tracer_provider(provider)
            self._provider = provider
            self._tracer = trace.get_tracer(self.service_name)
        except Exception as exc:
            log.warning("opentelemetry unavailable, using local span log: %s", exc)
            self._tracer = None

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        record = SpanRecord(name=name, attributes=dict(attributes))
        if not self.enabled:
            yield record
            return
        if self._tracer is None:
            self.spans.append(record)
            yield record
            return
        with self._tracer.start_as_current_span(name) as span:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v)
                except Exception:
                    span.set_attribute(k, str(v))
            self.spans.append(record)
            yield record

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "service_name": self.service_name,
            "spans": len(self.spans),
            "backend": "otel" if self._tracer is not None else "local",
        }


class _RecordingExporter:
    def __init__(self, telemetry: Telemetry):
        self.telemetry = telemetry

    def export(self, spans) -> int:
        # Spans already recorded in Telemetry.span(); exporter satisfies SDK contract.
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult
            return SpanExportResult.SUCCESS
        except Exception:
            return 0

    def shutdown(self) -> None:
        return None


def build_telemetry(enabled: bool, service_name: str = "quant-os-api") -> Telemetry:
    return Telemetry(enabled=enabled, service_name=service_name)
