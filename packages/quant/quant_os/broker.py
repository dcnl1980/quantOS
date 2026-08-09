from collections import defaultdict
from .models import Side,Fill

class PaperBroker:
    def __init__(self,initial_cash=100000,fees_bps=None,slippage_bps=2):
        self.initial_cash=initial_cash; self.cash=initial_cash
        self.realized_pnl=0; self.positions_qty=defaultdict(float); self.positions_cost=defaultdict(float)
        self.venue_exposure=defaultdict(float); self.fills=[]
        self.fees_bps=fees_bps or {}; self.slippage_bps=slippage_bps; self.peak_equity=initial_cash

    def execute(self,o):
        rate=self.fees_bps.get(o.venue,10)/10000; slip=self.slippage_bps/10000
        px=o.price*(1+slip if o.side==Side.BUY else 1-slip)
        fee=px*o.quantity*rate
        return self._apply(o, px, fee)

    def apply_external_fill(self, o, price, fee):
        """Ledger a venue-reported fill without re-applying local slippage/fees."""
        return self._apply(o, price, fee)

    def _apply(self, o, px, fee):
        n=px*o.quantity
        signed=o.quantity if o.side==Side.BUY else -o.quantity
        old=self.positions_qty[o.symbol]; cost=self.positions_cost[o.symbol]
        self.cash += (-n-fee if o.side==Side.BUY else n-fee)
        if old==0 or old*signed>0:
            new=old+signed
            self.positions_cost[o.symbol]=(abs(old)*cost+abs(signed)*px)/max(abs(new),1e-12)
        else:
            closing=min(abs(old),abs(signed))
            self.realized_pnl += ((px-cost)*closing if old>0 else (cost-px)*closing)-fee
            new=old+signed
            if new==0:self.positions_cost[o.symbol]=0
            elif old*new<0:self.positions_cost[o.symbol]=px
        self.positions_qty[o.symbol]=old+signed
        self.venue_exposure[o.venue]+=n
        f=Fill(o.id,o.venue,o.symbol,o.side,o.quantity,px,fee,o.strategy,o.opportunity_id)
        self.fills.append(f); return f

    def snapshot(self,marks=None):
        from .models import PortfolioSnapshot
        marks=marks or {}; unreal=0; inv=0
        for s,q in self.positions_qty.items():
            mark=marks.get(s,self.positions_cost[s]); inv+=q*mark
            if q>0:unreal+=(mark-self.positions_cost[s])*q
            elif q<0:unreal+=(self.positions_cost[s]-mark)*abs(q)
        eq=self.cash+inv; self.peak_equity=max(self.peak_equity,eq)
        dd=(self.peak_equity-eq)/self.peak_equity*100 if self.peak_equity else 0
        return PortfolioSnapshot(self.cash,eq,self.realized_pnl,unreal,self.peak_equity,max(0,dd),dict(self.positions_qty),dict(self.venue_exposure))
