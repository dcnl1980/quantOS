use serde_json::json;
use std::{env, sync::Arc, time::Instant};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{TcpListener, TcpStream},
    sync::Mutex,
};

#[derive(Clone)]
struct Config {
    initial_cash: f64,
    min_edge: f64,
    max_notional: f64,
    max_daily_loss: f64,
    max_drawdown: f64,
    max_slippage: f64,
    max_rejections: u64,
}
struct Engine {
    cash: f64,
    realized: f64,
    peak: f64,
    turnover: f64,
    trades: u64,
    rejects: u64,
    halted: bool,
    cfg: Config,
}
impl Engine {
    fn new(cfg: Config) -> Self {
        Self { cash: cfg.initial_cash, realized: 0.0, peak: cfg.initial_cash,
               turnover: 0.0, trades: 0, rejects: 0, halted: false, cfg }
    }
    fn snapshot(&self) -> serde_json::Value {
        let dd = if self.peak > 0.0 { ((self.peak-self.cash)/self.peak*100.0).max(0.0) } else {0.0};
        json!({"type":"snapshot","initial_cash":self.cfg.initial_cash,"cash":self.cash,"equity":self.cash,
               "realized_pnl":self.realized,"unrealized_pnl":0.0,"peak_equity":self.peak,
               "drawdown_pct":dd,"positions":{},"venue_exposure":{},"trade_count":self.trades,
               "rejection_count":self.rejects,"halted":self.halted,"turnover":self.turnover})
    }
    fn reject(&mut self, reason: &str, started: Instant, commit: bool) -> serde_json::Value {
        if commit {
            self.rejects += 1;
            if self.rejects >= self.cfg.max_rejections { self.halted = true; }
        }
        let dd = if self.peak > 0.0 { ((self.peak-self.cash)/self.peak*100.0).max(0.0) } else {0.0};
        json!({"type":"execution","allowed":false,"reason":reason,"approved_notional":0.0,
               "quantity":0.0,"buy_exec_price":0.0,"sell_exec_price":0.0,"buy_fee":0.0,"sell_fee":0.0,
               "trade_pnl":0.0,"realized_pnl":self.realized,"equity":self.cash,"drawdown_pct":dd,
               "latency_ns":started.elapsed().as_nanos() as u64,"trade_count":self.trades})
    }
    fn decide(&mut self, p: &[&str], commit: bool) -> serde_json::Value {
        let started=Instant::now();
        let cmd = p.first().copied().unwrap_or("");
        if p.len()!=13 || (cmd!="EXEC_ARB" && cmd!="EVAL_ARB") {
            return json!({"type":"error","error":"expected EXEC_ARB or EVAL_ARB with 12 fields"});
        }
        let nums: Result<Vec<f64>,_> = [5usize,6,7,8,9,10,11,12].iter().map(|&i| p[i].parse::<f64>()).collect();
        let n=match nums { Ok(v)=>v, Err(_)=>return json!({"type":"error","error":"invalid numeric field"}) };
        let (buy,sell,edge,maxn,desired,bfee,sfee,slip)=(n[0],n[1],n[2],n[3],n[4],n[5],n[6],n[7]);
        if self.halted { return self.reject("circuit_breaker_halted",started,commit); }
        if !buy.is_finite() || !sell.is_finite() || buy<=0.0 || sell<=buy { return self.reject("invalid_or_non_positive_spread",started,commit); }
        if edge<self.cfg.min_edge { return self.reject("edge_below_minimum",started,commit); }
        if slip>self.cfg.max_slippage { return self.reject("slippage_above_maximum",started,commit); }
        if self.realized<=-self.cfg.max_daily_loss { return self.reject("daily_loss_limit",started,commit); }
        let dd=if self.peak>0.0 { ((self.peak-self.cash)/self.peak*100.0).max(0.0) } else {0.0};
        if dd>=self.cfg.max_drawdown { return self.reject("drawdown_limit",started,commit); }

        let mut approved=desired.min(self.cfg.max_notional).min(self.cash.max(0.0)*0.05);
        if maxn>0.0 { approved=approved.min(maxn); }
        if approved<=0.0 { return self.reject("zero_approved_notional",started,commit); }

        let sr=slip/10000.0;
        let buy_exec=buy*(1.0+sr); let sell_exec=sell*(1.0-sr);
        let qty=approved/buy_exec;
        let bn=qty*buy_exec; let sn=qty*sell_exec;
        let bf=bn*bfee/10000.0; let sf=sn*sfee/10000.0;
        let pnl=sn-bn-bf-sf;
        let equity = if commit { self.cash + pnl } else { self.cash + pnl };
        let realized = if commit { self.realized + pnl } else { self.realized + pnl };
        if commit {
            self.cash+=pnl; self.realized+=pnl; self.peak=self.peak.max(self.cash);
            self.turnover+=bn+sn; self.trades+=1; if self.rejects>0 {self.rejects-=1;}
        }
        let dd=if self.peak>0.0 { ((self.peak-(if commit {self.cash} else {equity}))/self.peak*100.0).max(0.0) } else {0.0};
        json!({"type":"execution","allowed":true,"reason": if commit {"approved"} else {"shadow_approved"},
               "approved_notional":approved,
               "quantity":qty,"buy_exec_price":buy_exec,"sell_exec_price":sell_exec,
               "buy_fee":bf,"sell_fee":sf,"trade_pnl":pnl,"realized_pnl": if commit {self.realized} else {realized},
               "equity": if commit {self.cash} else {equity},"drawdown_pct":dd,
               "latency_ns":started.elapsed().as_nanos() as u64,
               "trade_count":self.trades})
    }
    fn execute(&mut self, p: &[&str]) -> serde_json::Value { self.decide(p, true) }
    fn evaluate(&mut self, p: &[&str]) -> serde_json::Value { self.decide(p, false) }
    fn reset(&mut self) {
        self.cash=self.cfg.initial_cash; self.realized=0.0; self.peak=self.cfg.initial_cash;
        self.turnover=0.0; self.trades=0; self.rejects=0; self.halted=false;
    }
}
fn envf(k:&str,d:f64)->f64 { env::var(k).ok().and_then(|x|x.parse().ok()).unwrap_or(d) }
fn envu(k:&str,d:u64)->u64 { env::var(k).ok().and_then(|x|x.parse().ok()).unwrap_or(d) }

async fn client(stream:TcpStream, engine:Arc<Mutex<Engine>>) {
    let (r,mut w)=stream.into_split(); let mut lines=BufReader::new(r).lines();
    while let Ok(Some(line))=lines.next_line().await {
        let response = if line=="PING" { json!({"type":"pong","engine":"rust-tokio"}) }
        else if line=="SNAPSHOT" { engine.lock().await.snapshot() }
        else if line=="RESET" { engine.lock().await.reset(); json!({"type":"reset","ok":true}) }
        else if line=="RESET_CB" { let mut e=engine.lock().await; e.rejects=0; e.halted=false; json!({"type":"reset_cb","ok":true}) }
        else {
            let parts:Vec<&str>=line.split('|').collect();
            let mut e=engine.lock().await;
            if parts.first().copied()==Some("EVAL_ARB") { e.evaluate(&parts) } else { e.execute(&parts) }
        };
        if w.write_all(format!("{}\n",response).as_bytes()).await.is_err(){break;}
    }
}
#[tokio::main]
async fn main() -> Result<(),Box<dyn std::error::Error>> {
    let cfg=Config{initial_cash:envf("INITIAL_CASH",100000.0),min_edge:envf("MIN_NET_EDGE_BPS",8.0),
        max_notional:envf("MAX_ORDER_NOTIONAL",2500.0),max_daily_loss:envf("MAX_DAILY_LOSS",3000.0),
        max_drawdown:envf("MAX_DRAWDOWN_PCT",5.0),max_slippage:envf("MAX_SLIPPAGE_BPS",15.0),
        max_rejections:envu("CIRCUIT_BREAKER_REJECTIONS",25)};
    let port=env::var("EXECUTION_ENGINE_PORT").unwrap_or_else(|_|"9100".to_string());
    let listener=TcpListener::bind(format!("0.0.0.0:{port}")).await?;
    let engine=Arc::new(Mutex::new(Engine::new(cfg)));
    println!("Quant Rust execution engine listening on 0.0.0.0:{port}");
    loop { let (s,_)=listener.accept().await?; let e=engine.clone(); tokio::spawn(async move{client(s,e).await;}); }
}


#[cfg(test)]
mod tests {
    use super::*;
    fn cfg() -> Config {
        Config { initial_cash:100000.0,min_edge:8.0,max_notional:2500.0,max_daily_loss:3000.0,
                 max_drawdown:5.0,max_slippage:15.0,max_rejections:25 }
    }
    #[test]
    fn executes_positive_arb_and_rejects_low_edge() {
        let mut e=Engine::new(cfg());
        let p=["EXEC_ARB","id","BTCUSDT","a","b","100","101","50","10000","5000","5","5","2"];
        let v=e.execute(&p);
        assert_eq!(v["allowed"], true);
        assert!(v["trade_pnl"].as_f64().unwrap() > 0.0);
        assert_eq!(e.trades,1);

        let p2=["EXEC_ARB","id2","BTCUSDT","a","b","100","101","2","10000","1000","5","5","2"];
        let v2=e.execute(&p2);
        assert_eq!(v2["allowed"], false);
        assert_eq!(v2["reason"], "edge_below_minimum");
    }

    #[test]
    fn shadow_evaluate_does_not_mutate() {
        let mut e=Engine::new(cfg());
        let p=["EVAL_ARB","id","BTCUSDT","a","b","100","101","50","10000","5000","5","5","2"];
        let v=e.evaluate(&p);
        assert_eq!(v["allowed"], true);
        assert_eq!(v["reason"], "shadow_approved");
        assert_eq!(e.trades, 0);
        assert!((e.cash - 100000.0).abs() < 1e-9);
    }
}
