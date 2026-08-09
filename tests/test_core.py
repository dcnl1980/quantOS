from quant_os.models import Quote,Opportunity,OpportunityType,PortfolioSnapshot,OrderRequest,Side
from quant_os.costs import CostModel
from quant_os.strategies.arbitrage import CrossVenueArbitrage
from quant_os.risk import RiskEngine,RiskConfig
from quant_os.broker import PaperBroker
from quant_os.backtest import ArbitrageBacktester

def test_arbitrage_detects_net_edge():
    s=CrossVenueArbitrage(CostModel({"a":5,"b":5},2),5)
    ops=s.scan([Quote("a","BTCUSDT",99.99,100,10,10),Quote("b","BTCUSDT",100.30,100.31,10,10)])
    assert ops and ops[0].buy_venue=="a" and ops[0].net_edge_bps>5

def test_costs_can_remove_edge():
    s=CrossVenueArbitrage(CostModel({"a":10,"b":10},3),1)
    assert not s.scan([Quote("a","X",99.99,100,10,10),Quote("b","X",100.10,100.11,10,10)])

def test_risk_caps_order():
    op=Opportunity("X",OpportunityType.CROSS_VENUE,"a","b",100,101,100,20,.9,10000)
    p=PortfolioSnapshot(100000,100000,0,0,100000,0,{}, {})
    d=RiskEngine(RiskConfig(max_order_notional=2500,min_net_edge_bps=8)).evaluate(op,p,5000)
    assert d.allowed and d.approved_notional==2500

def test_paper_paired_trade():
    b=PaperBroker(10000,{"a":0,"b":0},0)
    b.execute(OrderRequest("a","X",Side.BUY,10,100,"arb"))
    b.execute(OrderRequest("b","X",Side.SELL,10,101,"arb"))
    assert round(b.snapshot({"X":100.5}).equity,2)==10010

def test_backtest():
    s=CrossVenueArbitrage(CostModel({"a":0,"b":0},0),1)
    r=ArbitrageBacktester(s,1000).run([[Quote("a","X",99,100,10,10),Quote("b","X",101,102,10,10)]])
    assert r.traded==1 and r.net_pnl>0
