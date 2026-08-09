from quant_os.models import Opportunity,OpportunityType

class LeadLagDetector:
    # Analysis-only signal; it is never auto-executed by the runtime.
    def __init__(self,move_threshold_bps=12,divergence_threshold_bps=8):
        self.move_threshold_bps=move_threshold_bps
        self.divergence_threshold_bps=divergence_threshold_bps

    def scan(self,histories):
        returns={}; latest={}
        for venue,h in histories.items():
            if len(h)<5: continue
            returns[venue]=(h[-1].mid/h[-5].mid-1)*10000
            latest[venue]=h[-1]
        if len(returns)<2: return []
        leader=max(returns,key=lambda v:abs(returns[v]))
        if abs(returns[leader])<self.move_threshold_bps: return []
        out=[]
        for lagger,r in returns.items():
            if lagger==leader: continue
            div=returns[leader]-r
            if abs(div)<self.divergence_threshold_bps: continue
            buy,sell=(lagger,leader) if div>0 else (leader,lagger)
            out.append(Opportunity(
                latest[leader].symbol,OpportunityType.LEAD_LAG,buy,sell,
                latest[buy].ask,latest[sell].bid,abs(div),abs(div),
                min(.9,.5+abs(div)/250),0,
                metadata={"leader":leader,"returns_bps":returns,"auto_execute":False}
            ))
        return out
