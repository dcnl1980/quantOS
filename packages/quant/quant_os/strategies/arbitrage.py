from quant_os.models import Opportunity,OpportunityType
from quant_os.costs import CostModel

class CrossVenueArbitrage:
    name="cross_venue_arbitrage"
    def __init__(self,costs:CostModel,min_net_edge_bps=8):
        self.costs=costs; self.min_net_edge_bps=min_net_edge_bps

    def scan(self,quotes):
        out=[]
        for buy in quotes:
            for sell in quotes:
                if buy.venue==sell.venue or buy.ask<=0 or sell.bid<=buy.ask:
                    continue
                gross=((sell.bid-buy.ask)/buy.ask)*10000
                net=self.costs.net_edge_bps(gross,buy.venue,sell.venue)
                if net<self.min_net_edge_bps:
                    continue
                depth=min(buy.ask*max(buy.ask_size,.01),sell.bid*max(sell.bid_size,.01))
                out.append(Opportunity(
                    buy.symbol,OpportunityType.CROSS_VENUE,buy.venue,sell.venue,
                    buy.ask,sell.bid,gross,net,min(.99,.55+net/200),depth,
                    metadata={"estimated_cost_bps":gross-net}
                ))
        return sorted(out,key=lambda x:x.net_edge_bps,reverse=True)
