from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid

def utcnow():
    return datetime.now(timezone.utc)

class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OpportunityType(StrEnum):
    CROSS_VENUE = "cross_venue"
    LEAD_LAG = "lead_lag"

@dataclass(slots=True)
class Quote:
    venue: str
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    exchange_ts: datetime = field(default_factory=utcnow)
    received_ts: datetime = field(default_factory=utcnow)
    sequence: int | None = None

    @property
    def mid(self):
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self):
        return ((self.ask-self.bid)/self.mid)*10000 if self.mid else 0

    def to_dict(self):
        d = asdict(self)
        d["exchange_ts"] = self.exchange_ts.isoformat()
        d["received_ts"] = self.received_ts.isoformat()
        d["mid"] = self.mid
        d["spread_bps"] = self.spread_bps
        return d

@dataclass(slots=True)
class Opportunity:
    symbol: str
    type: OpportunityType
    buy_venue: str
    sell_venue: str
    buy_price: float
    sell_price: float
    gross_edge_bps: float
    net_edge_bps: float
    confidence: float
    max_notional: float
    observed_at: datetime = field(default_factory=utcnow)
    metadata: dict[str,Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self):
        d = asdict(self)
        d["type"] = self.type.value
        d["observed_at"] = self.observed_at.isoformat()
        return d

@dataclass(slots=True)
class OrderRequest:
    venue: str
    symbol: str
    side: Side
    quantity: float
    price: float
    strategy: str
    opportunity_id: str|None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass(slots=True)
class Fill:
    order_id: str
    venue: str
    symbol: str
    side: Side
    quantity: float
    price: float
    fee: float
    strategy: str
    opportunity_id: str|None
    ts: datetime = field(default_factory=utcnow)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self):
        d=asdict(self); d["side"]=self.side.value; d["ts"]=self.ts.isoformat(); return d

@dataclass(slots=True)
class PortfolioSnapshot:
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    peak_equity: float
    drawdown_pct: float
    positions: dict[str,float]
    venue_exposure: dict[str,float]
