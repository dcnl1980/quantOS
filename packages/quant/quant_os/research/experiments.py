"""In-memory experiment registry with promotion status."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import StrEnum
from typing import Any

from quant_os.models import utcnow


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclass
class ExperimentRecord:
    name: str
    strategy_id: str
    hypothesis: str
    params: dict[str, Any] = field(default_factory=dict)
    dataset: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.DRAFT
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d


class ExperimentRegistry:
    def __init__(self):
        self._items: dict[str, ExperimentRecord] = {}

    def create(
        self,
        name: str,
        strategy_id: str,
        hypothesis: str,
        params: dict | None = None,
        dataset: dict | None = None,
    ) -> ExperimentRecord:
        rec = ExperimentRecord(
            name=name,
            strategy_id=strategy_id,
            hypothesis=hypothesis,
            params=dict(params or {}),
            dataset=dict(dataset or {}),
        )
        self._items[rec.id] = rec
        return rec

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        return self._items.get(experiment_id)

    def list(self, limit: int = 50) -> list[ExperimentRecord]:
        items = sorted(self._items.values(), key=lambda r: r.created_at, reverse=True)
        return items[: max(1, min(limit, 500))]

    def update_status(self, experiment_id: str, status: ExperimentStatus, note: str | None = None):
        rec = self._items[experiment_id]
        rec.status = status
        rec.updated_at = utcnow()
        if note:
            rec.notes.append(note)
        return rec

    def complete(
        self,
        experiment_id: str,
        metrics: dict[str, Any],
        artifacts: dict[str, Any] | None = None,
    ) -> ExperimentRecord:
        rec = self._items[experiment_id]
        rec.metrics = dict(metrics)
        rec.artifacts = dict(artifacts or {})
        rec.status = ExperimentStatus.COMPLETED
        rec.updated_at = utcnow()
        return rec

    def fail(self, experiment_id: str, reason: str) -> ExperimentRecord:
        return self.update_status(experiment_id, ExperimentStatus.FAILED, reason)

    def snapshot(self) -> dict:
        by_status: dict[str, int] = {}
        for rec in self._items.values():
            by_status[rec.status.value] = by_status.get(rec.status.value, 0) + 1
        return {
            "count": len(self._items),
            "by_status": by_status,
            "recent": [r.to_dict() for r in self.list(20)],
        }
