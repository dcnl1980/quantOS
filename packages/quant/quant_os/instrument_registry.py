"""Canonical instrument registry with venue listings and quote currency metadata."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable


@dataclass(slots=True)
class VenueListing:
    venue: str
    venue_symbol: str
    tick_size: float = 0.01
    lot_size: float = 0.0001
    min_notional: float = 10.0


@dataclass(slots=True)
class Instrument:
    symbol: str
    base: str
    quote: str
    underlying: str
    settlement: str
    listings: list[VenueListing] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        return d


class InstrumentRegistry:
    def __init__(self, instruments: Iterable[Instrument] | None = None):
        self._by_symbol: dict[str, Instrument] = {}
        for inst in instruments or []:
            self.register(inst)

    @classmethod
    def default(cls, symbols: Iterable[str] | None = None) -> "InstrumentRegistry":
        symbols = list(symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        reg = cls()
        for symbol in symbols:
            base, quote = _split_symbol(symbol)
            underlying = base
            settlement = quote
            listings = [
                VenueListing("binance", symbol, tick_size=0.01, lot_size=0.0001, min_notional=10),
                VenueListing(
                    "coinbase",
                    f"{base}-USD" if quote in {"USDT", "USD"} else symbol,
                    tick_size=0.01,
                    lot_size=0.0001,
                    min_notional=10,
                ),
                VenueListing("sim_a", symbol),
                VenueListing("sim_b", symbol),
            ]
            reg.register(Instrument(symbol, base, quote, underlying, settlement, listings))
        return reg

    def register(self, instrument: Instrument):
        self._by_symbol[instrument.symbol.upper()] = instrument

    def get(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def symbols(self) -> list[str]:
        return sorted(self._by_symbol)

    def listing(self, venue: str, symbol: str) -> VenueListing | None:
        inst = self.get(symbol)
        if not inst:
            return None
        venue = venue.lower()
        for listing in inst.listings:
            if listing.venue == venue:
                return listing
        return None

    def quote_currency(self, symbol: str) -> str | None:
        inst = self.get(symbol)
        return inst.quote if inst else None

    def graph(self) -> dict:
        nodes = {}
        edges = []
        for inst in self._by_symbol.values():
            sid = f"symbol:{inst.symbol}"
            nodes[sid] = {"id": sid, "type": "instrument", "label": inst.symbol, "base": inst.base, "quote": inst.quote}
            uid = f"underlying:{inst.underlying}"
            nodes[uid] = {"id": uid, "type": "underlying", "label": inst.underlying}
            edges.append({"source": sid, "target": uid, "type": "DERIVED_FROM"})
            qid = f"currency:{inst.quote}"
            nodes[qid] = {"id": qid, "type": "currency", "label": inst.quote}
            edges.append({"source": sid, "target": qid, "type": "PRICED_IN"})
            for listing in inst.listings:
                vid = f"venue:{listing.venue}"
                nodes[vid] = {"id": vid, "type": "venue", "label": listing.venue}
                edges.append({
                    "source": sid,
                    "target": vid,
                    "type": "LISTED_ON",
                    "venue_symbol": listing.venue_symbol,
                })
        return {"nodes": list(nodes.values()), "edges": edges}

    def to_list(self) -> list[dict]:
        return [i.to_dict() for i in self._by_symbol.values()]


def _split_symbol(symbol: str) -> tuple[str, str]:
    symbol = symbol.upper()
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, "USD"
