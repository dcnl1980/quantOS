'use client'
import {useEffect,useState} from 'react'
import {Activity,ShieldCheck,Radio,Zap,BarChart3,CircleDollarSign} from 'lucide-react'
type Obj=Record<string,any>
const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000'
const money=(n:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n||0)
const num=(n:number,d=2)=>Number(n||0).toFixed(d)

export default function Page(){
 const [snap,setSnap]=useState<Obj>({}),[ops,setOps]=useState<Obj[]>([]),[fills,setFills]=useState<Obj[]>([])
 const [shadowFills,setShadowFills]=useState<Obj[]>([])
 const [quotes,setQuotes]=useState<Record<string,Obj>>({}),[events,setEvents]=useState<Obj[]>([]),[connected,setConnected]=useState(false)
 const [bt,setBt]=useState<Obj|null>(null)
 const [research,setResearch]=useState<Obj|null>(null)
 useEffect(()=>{
  fetch(`${API}/api/v1/snapshot`).then(r=>r.json()).then(s=>{setSnap(s);setOps(s.opportunities||[]);setFills(s.fills||[]);setShadowFills(s.shadow_fills||[]);let q:Record<string,Obj>={};(s.quotes||[]).forEach((x:Obj)=>q[`${x.venue}:${x.symbol}`]=x);setQuotes(q)}).catch(()=>{})
  const ws=new WebSocket(API.replace(/^http/,'ws')+'/ws')
  ws.onopen=()=>setConnected(true);ws.onclose=()=>setConnected(false)
  ws.onmessage=m=>{const e=JSON.parse(m.data);const d=e.data||{}
   if(e.type==='snapshot'){setSnap(d);setOps(d.opportunities||[]);setFills(d.fills||[]);setShadowFills(d.shadow_fills||[])}
   if(e.type==='quote')setQuotes(p=>({...p,[`${d.venue}:${d.symbol}`]:d}))
   if(e.type==='opportunity')setOps(p=>[d,...p].slice(0,50))
   if(e.type==='fill')setFills(p=>[d,...p].slice(0,50))
   if(e.type==='shadow_fill')setShadowFills(p=>[d,...p].slice(0,50))
   if(e.type==='portfolio')setSnap(p=>({...p,portfolio:d}))
   setEvents(p=>[e,...p].slice(0,10))
  };return()=>ws.close()
 },[])
 const qs=Object.values(quotes).sort((a,b)=>a.symbol.localeCompare(b.symbol)||a.venue.localeCompare(b.venue))
 const p=snap.portfolio||{},stats=snap.stats||{},pnl=(p.equity||0)-100000
 const execMode=(snap.execution_mode||(snap.shadow_trading?'shadow':snap.testnet_trading?'testnet':'paper')).toUpperCase()
 const execLabel=execMode==='SHADOW'?'SHADOW (NO ORDERS)':execMode==='TESTNET'?'TESTNET ROUTER':execMode==='LIVE'?'LIVE BLOCKED':'PAPER EXECUTION'
 async function backtest(){setBt({loading:true});const r=await fetch(`${API}/api/v1/backtest/demo?ticks=5000&notional=1000`,{method:'POST'});setBt(await r.json())}
 async function runResearch(){setResearch({loading:true});const r=await fetch(`${API}/api/v1/research/suite?ticks=2400&mc_runs=20&seed=7`,{method:'POST'});setResearch(await r.json())}
 return <main>
  <header><div><div className="eyebrow"><Radio size={14}/> QUANT INTELLIGENCE TERMINAL</div><h1>Quant OS</h1></div>
   <div className="status"><span className={connected?'dot live':'dot'}/>{connected?'LIVE STREAM':'RECONNECTING'}<span className="pill">{(snap.market_mode||snap.mode||'...').toUpperCase()}</span><span className="pill safe">{execLabel}</span></div></header>
  <section className="kpis">
   <Card icon={<CircleDollarSign/>} label="Portfolio equity" value={money(p.equity)} sub={`Cash ${money(p.cash)}`}/>
   <Card icon={<BarChart3/>} label="Session P&L" value={money(pnl)} sub={`Drawdown ${num(p.drawdown_pct)}%`}/>
   <Card icon={<Zap/>} label="Opportunities" value={String(stats.opportunities||0)} sub={`${stats.trades||0} trades / ${stats.shadow_trades||0} shadow / ${stats.hedges||0} hedges`}/>
   <Card icon={<ShieldCheck/>} label="Risk engine" value={snap.risk?.halted?'HALTED':'ARMED'} sub={`${snap.risk?.rejections||0} rejects`}/>
   <Card icon={<Activity/>} label="Execution engine" value={(snap.execution_engine||'...').toUpperCase()} sub={`${num((snap.execution?.last_latency_ns||0)/1000,1)} µs last decision`}/>
  </section>
  <section className="grid mainGrid">
   <Panel title="Market Matrix" right={`${qs.length} streams`}><table><thead><tr><th>Symbol</th><th>Venue</th><th>Bid</th><th>Ask</th><th>Spread</th></tr></thead>
   <tbody>{qs.slice(0,20).map(q=><tr key={`${q.venue}:${q.symbol}`}><td className="strong">{q.symbol}</td><td><span className="venue">{q.venue}</span></td><td>{num(q.bid,q.bid>1000?2:4)}</td><td>{num(q.ask,q.ask>1000?2:4)}</td><td>{num(q.spread_bps)} bp</td></tr>)}</tbody></table></Panel>
   <Panel title="Executable Edge" right="cost-adjusted"><div className="opList">{ops.filter(o=>o.type==='cross_venue').slice(0,8).map(o=><div className="op" key={o.id}><div><b>{o.symbol}</b><small>{o.buy_venue} → {o.sell_venue}</small></div><div className="edge">+{num(o.net_edge_bps)} bp<small>{num(o.confidence*100,0)}% confidence</small></div></div>)}</div></Panel>
  </section>
  <section className="grid lowerGrid">
   <Panel title={execMode==='SHADOW'?'Shadow Decision Log':execMode==='TESTNET'?'Testnet Execution Log':'Paper Execution Log'} right={`${(execMode==='SHADOW'?shadowFills:fills).length} rows`}><table><thead><tr><th>Time</th><th>Side</th><th>Venue</th><th>Symbol</th><th>Qty</th><th>Price</th></tr></thead>
   <tbody>{(execMode==='SHADOW'?shadowFills:fills).slice(0,10).map(f=><tr key={f.id}><td>{new Date(f.ts).toLocaleTimeString()}</td><td className={f.side==='buy'?'buy':'sell'}>{f.side.toUpperCase()}</td><td>{f.venue}</td><td>{f.symbol}</td><td>{num(f.quantity,6)}</td><td>{money(f.price)}</td></tr>)}</tbody></table></Panel>
   <Panel title="Strategy Lab" right="research"><div className="lab"><h3>Cross-venue arbitrage</h3><p>Replay backtests plus H3 walk-forward, Monte Carlo and promotion gates.</p>
    <div style={{display:'flex',gap:8,flexWrap:'wrap'}}><button onClick={backtest}>Run backtest</button><button onClick={runResearch}>Run research suite</button></div>
    {bt&&!bt.loading&&<div className="result"><Metric l="Net P&L" v={money(bt.net_pnl)}/><Metric l="Trades" v={String(bt.traded)}/><Metric l="Win rate" v={`${bt.win_rate}%`}/><Metric l="Costs" v={money(bt.estimated_costs)}/></div>}
    {research&&!research.loading&&<div className="result"><Metric l="OOS P&L" v={money(research.metrics?.oos_net_pnl)}/><Metric l="Stability" v={num(research.metrics?.stability_score,2)}/><Metric l="MC p05" v={money(research.metrics?.p05_net_pnl)}/><Metric l="Promote" v={research.promotion?.approved?'YES':'NO'}/></div>}</div></Panel>
  </section>
  <section className="grid footerGrid">
   <Panel title="Risk Guardrails"><div className="guards"><Guard a="Minimum net edge" b="8 bp"/><Guard a="Max order notional" b="$2,500"/><Guard a="Max daily loss" b="$3,000"/><Guard a="Max drawdown" b="5%"/><Guard a="Max slippage" b="15 bp"/><Guard a="Execution" b={execLabel}/><Guard a="USDT/USD basis" b={`${num(snap.basis?.basis_bps||0,1)} bp`}/><Guard a="Data plane" b={(snap.data_plane?.bus?.backend||'off').toString()}/><Guard a="Open orders" b={String(stats.open_orders||0)}/><Guard a="Experiments" b={String(snap.research?.experiments?.count||0)}/><Guard a="Strategy status" b={(snap.research?.governance?.statuses?.cross_venue_arbitrage||'candidate').toString()}/></div></Panel>
   <Panel title="Live Event Bus" right={<Activity size={15}/>}><div className="events">{events.slice(0,7).map((e,i)=><div key={i}><span>{e.type}</span><code>{summary(e)}</code></div>)}</div></Panel>
  </section>
  <footer>QUANT OS / deterministic execution core / AI-ready research layer / paper mode by default</footer>
 </main>
}
function summary(e:any){let d=e.data||{};if(e.type==='quote')return `${d.venue} ${d.symbol} ${num(d.mid)}`;if(e.type==='opportunity')return `${d.symbol} +${num(d.net_edge_bps,1)}bp`;if(e.type==='fill'||e.type==='shadow_fill')return `${d.side} ${d.symbol} @ ${num(d.price)}`;if(e.type==='risk_decision')return `${d.allowed?'allow':'reject'} ${d.reason}`;if(e.type==='book')return `${d.venue} ${d.symbol} ${d.status}`;if(e.type==='user_stream')return `${d.venue} ${d.event_type}`;if(e.type==='reconciliation')return `${d.mismatch_count||0} mismatches`;if(e.type==='hedge')return `${d.action||''} ${d.reason||''}`;if(e.type==='execution_session')return `${d.symbol} ${d.hedge?.action||''}`;return ''}
function Card({icon,label,value,sub}:any){return <div className="card"><div className="ico">{icon}</div><div><small>{label}</small><strong>{value}</strong><span>{sub}</span></div></div>}
function Panel({title,right,children}:any){return <div className="panel"><div className="panelHead"><h2>{title}</h2><div>{right}</div></div>{children}</div>}
function Metric({l,v}:any){return <div><small>{l}</small><b>{v}</b></div>} function Guard({a,b}:any){return <div><span>{a}</span><b>{b}</b></div>}
