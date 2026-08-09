from dataclasses import dataclass

@dataclass(slots=True)
class RiskConfig:
    max_order_notional: float=2500
    max_symbol_exposure: float=15000
    max_venue_exposure: float=30000
    max_daily_loss: float=3000
    max_drawdown_pct: float=5
    max_slippage_bps: float=15
    min_net_edge_bps: float=8
    circuit_breaker_rejections: int=25

@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    approved_notional: float=0

class RiskEngine:
    def __init__(self,config):
        self.config=config; self.rejections=0; self.halted=False

    def reset_circuit_breaker(self):
        self.rejections=0; self.halted=False

    def reject(self,reason):
        self.rejections+=1
        if self.rejections>=self.config.circuit_breaker_rejections:self.halted=True
        return RiskDecision(False,reason)

    def evaluate(self,op,p,desired_notional,estimated_slippage_bps=2):
        if self.halted:return RiskDecision(False,"circuit_breaker_halted")
        if op.net_edge_bps<self.config.min_net_edge_bps:return self.reject("edge_below_minimum")
        if estimated_slippage_bps>self.config.max_slippage_bps:return self.reject("slippage_above_maximum")
        if p.realized_pnl<=-self.config.max_daily_loss:return self.reject("daily_loss_limit")
        if p.drawdown_pct>=self.config.max_drawdown_pct:return self.reject("drawdown_limit")
        sym=abs(p.positions.get(op.symbol,0))*op.buy_price
        if sym>=self.config.max_symbol_exposure:return self.reject("symbol_exposure_limit")
        if any(p.venue_exposure.get(v,0)>=self.config.max_venue_exposure for v in (op.buy_venue,op.sell_venue)):
            return self.reject("venue_exposure_limit")
        approved=min(desired_notional,self.config.max_order_notional,op.max_notional or desired_notional,max(0,p.equity*.05))
        if approved<=0:return self.reject("zero_notional")
        self.rejections=max(0,self.rejections-1)
        return RiskDecision(True,"approved",approved)
