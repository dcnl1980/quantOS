"""Shared ontology node/edge and contradiction types."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    INSTRUMENT = "instrument"
    VENUE = "venue"
    UNDERLYING = "underlying"
    CURRENCY = "currency"
    SETTLEMENT_SOURCE = "settlement_source"
    PREDICTION_MARKET = "prediction_market"
    OUTCOME = "outcome"


class EdgeType(str, Enum):
    LISTED_ON = "LISTED_ON"
    DERIVED_FROM = "DERIVED_FROM"
    PRICED_IN = "PRICED_IN"
    HEDGES = "HEDGES"
    CORRELATED_WITH = "CORRELATED_WITH"
    SETTLES_FROM = "SETTLES_FROM"
    DETECTED_BY = "DETECTED_BY"
    CAUSED_BY = "CAUSED_BY"
    ARBITRAGE_WITH = "ARBITRAGE_WITH"
    BASIS = "BASIS"
    COMPLEMENTS = "COMPLEMENTS"
    OUTCOME_OF = "OUTCOME_OF"


class ContradictionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(slots=True)
class GraphNode:
    id: str
    type: str
    label: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"id": self.id, "type": self.type, "label": self.label}
        d.update(self.attrs)
        return d


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    type: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"source": self.source, "target": self.target, "type": self.type}
        d.update(self.attrs)
        return d


@dataclass(slots=True)
class Contradiction:
    id: str
    kind: str
    severity: str
    message: str
    nodes: list[str] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
