from dataclasses import dataclass

@dataclass(slots=True)
class CostModel:
    venue_fee_bps: dict[str,float]
    default_slippage_bps: float=2.0

    def round_trip_cost_bps(self,buy_venue,sell_venue,slippage_bps=None):
        slip=self.default_slippage_bps if slippage_bps is None else slippage_bps
        return self.venue_fee_bps.get(buy_venue,10)+self.venue_fee_bps.get(sell_venue,10)+2*slip

    def net_edge_bps(self,gross,buy_venue,sell_venue,slippage_bps=None):
        return gross-self.round_trip_cost_bps(buy_venue,sell_venue,slippage_bps)
