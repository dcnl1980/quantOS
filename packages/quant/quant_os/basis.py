"""USD/USDT basis model for cross-venue quote normalization."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BasisSample:
    pair: str
    mid: float
    source: str


@dataclass(slots=True)
class BasisModel:
    """
    Converts venue quote currencies into a common settlement currency.

    `usdt_usd` is units of USD per 1 USDT. A value of 0.999 means USDT trades
    at a 10 bp discount to USD.
    """
    usdt_usd: float = 1.0
    source: str = "parity"

    def set_usdt_usd(self, mid: float, source: str = "manual"):
        if mid <= 0:
            raise ValueError("basis mid must be positive")
        self.usdt_usd = mid
        self.source = source

    def convert(self, price: float, from_ccy: str, to_ccy: str = "USD") -> float:
        from_ccy = from_ccy.upper()
        to_ccy = to_ccy.upper()
        if from_ccy == to_ccy:
            return price
        usd = self._to_usd(price, from_ccy)
        return self._from_usd(usd, to_ccy)

    def normalize_quote_prices(self, bid: float, ask: float, quote_ccy: str, to_ccy: str = "USD") -> tuple[float, float]:
        return self.convert(bid, quote_ccy, to_ccy), self.convert(ask, quote_ccy, to_ccy)

    def basis_bps(self) -> float:
        # Positive => USDT premium over USD.
        return (self.usdt_usd - 1.0) * 10_000

    def to_dict(self) -> dict:
        return {
            "usdt_usd": self.usdt_usd,
            "basis_bps": self.basis_bps(),
            "source": self.source,
        }

    def _to_usd(self, price: float, ccy: str) -> float:
        if ccy == "USD":
            return price
        if ccy == "USDT":
            return price * self.usdt_usd
        if ccy == "USDC":
            return price  # treated as USD-par unless extended
        raise ValueError(f"unsupported currency: {ccy}")

    def _from_usd(self, price_usd: float, ccy: str) -> float:
        if ccy == "USD":
            return price_usd
        if ccy == "USDT":
            return price_usd / self.usdt_usd
        if ccy == "USDC":
            return price_usd
        raise ValueError(f"unsupported currency: {ccy}")
