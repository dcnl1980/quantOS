"""Local vs venue order/fill reconciliation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import utcnow
from .orders import Order, OrderState, OrderStateMachine


@dataclass(slots=True)
class VenueOrderReport:
    client_order_id: str
    venue_order_id: str
    state: str
    filled_qty: float
    avg_fill_price: float
    fee: float = 0.0


@dataclass(slots=True)
class ReconMismatch:
    client_order_id: str
    field: str
    local: Any
    venue: Any
    severity: str = "warning"


@dataclass
class Reconciler:
    fsm: OrderStateMachine
    mismatches: list[ReconMismatch] = field(default_factory=list)
    last_run: datetime | None = None
    runs: int = 0
    auto_repair: bool = True

    def reconcile(self, reports: list[VenueOrderReport]) -> dict:
        self.runs += 1
        self.last_run = utcnow()
        found: list[ReconMismatch] = []
        report_ids = {r.client_order_id for r in reports}

        for report in reports:
            local = self.fsm.get(report.client_order_id)
            if local is None:
                found.append(ReconMismatch(
                    report.client_order_id, "presence", "missing", "present", "critical"
                ))
                continue
            if local.state == OrderState.NEW and report.venue_order_id:
                if self.auto_repair:
                    self.fsm.accept(local.client_order_id, report.venue_order_id)
                    local = self.fsm.get(report.client_order_id) or local
                else:
                    found.append(ReconMismatch(
                        report.client_order_id, "state", "new", report.state, "critical",
                    ))
            if local.venue_order_id and local.venue_order_id != report.venue_order_id:
                found.append(ReconMismatch(
                    report.client_order_id, "venue_order_id",
                    local.venue_order_id, report.venue_order_id, "critical",
                ))
            if abs(local.filled_qty - report.filled_qty) > 1e-9:
                found.append(ReconMismatch(
                    report.client_order_id, "filled_qty",
                    local.filled_qty, report.filled_qty, "critical",
                ))
                repairable = local.state in {
                    OrderState.ACCEPTED,
                    OrderState.PARTIALLY_FILLED,
                    OrderState.CANCEL_PENDING,
                    OrderState.REPLACE_PENDING,
                }
                if self.auto_repair and repairable and report.filled_qty > local.filled_qty:
                    delta = report.filled_qty - local.filled_qty
                    self.fsm.apply_fill(
                        local.client_order_id, delta, report.avg_fill_price, report.fee
                    )
            venue_state = _normalize_state(report.state)
            if venue_state and local.state != venue_state and not (
                local.state == OrderState.CANCEL_PENDING and venue_state == OrderState.CANCELLED
            ):
                # Soft mismatch while in-flight cancel/replace is expected.
                if local.state not in {
                    OrderState.CANCEL_PENDING, OrderState.REPLACE_PENDING
                }:
                    found.append(ReconMismatch(
                        report.client_order_id, "state",
                        local.state.value, report.state, "warning",
                    ))

        for order in self.fsm.open_orders():
            if order.client_order_id not in report_ids and order.state not in {
                OrderState.NEW, OrderState.CANCEL_PENDING, OrderState.REPLACE_PENDING
            }:
                found.append(ReconMismatch(
                    order.client_order_id, "presence", "present", "missing", "warning"
                ))

        self.mismatches.extend(found)
        if len(self.mismatches) > 1000:
            self.mismatches = self.mismatches[-500:]
        return {
            "runs": self.runs,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "mismatch_count": len(found),
            "mismatches": [
                {
                    "client_order_id": m.client_order_id,
                    "field": m.field,
                    "local": m.local,
                    "venue": m.venue,
                    "severity": m.severity,
                }
                for m in found
            ],
            "critical": sum(1 for m in found if m.severity == "critical"),
        }

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "total_mismatches": len(self.mismatches),
            "recent": [
                {
                    "client_order_id": m.client_order_id,
                    "field": m.field,
                    "local": m.local,
                    "venue": m.venue,
                    "severity": m.severity,
                }
                for m in self.mismatches[-20:]
            ],
        }


def _normalize_state(raw: str) -> OrderState | None:
    key = raw.lower().replace(" ", "_")
    mapping = {
        "new": OrderState.NEW,
        "accepted": OrderState.ACCEPTED,
        "open": OrderState.ACCEPTED,
        "partially_filled": OrderState.PARTIALLY_FILLED,
        "partial": OrderState.PARTIALLY_FILLED,
        "filled": OrderState.FILLED,
        "canceled": OrderState.CANCELLED,
        "cancelled": OrderState.CANCELLED,
        "rejected": OrderState.REJECTED,
        "replaced": OrderState.REPLACED,
    }
    return mapping.get(key)
