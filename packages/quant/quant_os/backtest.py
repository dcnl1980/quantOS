from dataclasses import dataclass,asdict

@dataclass(slots=True)
class BacktestResult:
    ticks:int; opportunities:int; traded:int; gross_pnl:float; estimated_costs:float; net_pnl:float; win_rate:float
    def to_dict(self):return asdict(self)

class ArbitrageBacktester:
    def __init__(self,strategy,notional=1000):self.strategy=strategy; self.notional=notional
    def run(self,batches):
        ticks=ops=traded=wins=0; gross=costs=0
        for quotes in batches:
            ticks+=1; found=self.strategy.scan(quotes); ops+=len(found)
            if not found:continue
            o=found[0]; n=min(self.notional,o.max_notional or self.notional)
            g=n*o.gross_edge_bps/10000; net=n*o.net_edge_bps/10000
            traded+=1; gross+=g; costs+=g-net; wins+=int(net>0)
        return BacktestResult(ticks,ops,traded,round(gross,2),round(costs,2),round(gross-costs,2),round(wins/traded*100 if traded else 0,2))
