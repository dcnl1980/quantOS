# Quant OS

A runnable, paper-first real-time market intelligence, arbitrage detection, risk and execution platform.

## Included

- Binance Spot real-time `bookTicker` WebSocket adapter
- Coinbase Advanced Trade ticker WebSocket adapter
- deterministic two-venue market simulator
- normalized quote model and market state
- cross-venue arbitrage detector
- cost model: fees + slippage
- lead/lag analysis detector
- central risk engine and circuit breaker
- paper broker, positions, fills, P&L and drawdown
- replay backtester
- FastAPI REST + WebSocket API
- PostgreSQL persistence
- Next.js live terminal dashboard
- Docker Compose deployment
- tests, SQL schema, security and operations docs
- explicit extension boundaries for Polymarket and live authenticated routing

**Default execution mode is PAPER.** An apparent spread is not guaranteed profit. Fees, slippage, latency,
partial fills, inventory, quote-currency basis, transfer restrictions and market impact can eliminate it.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- API: http://localhost:8000/api/v1/snapshot

The default simulator creates temporary cross-venue dislocations so the whole pipeline is visible immediately.

## Test

```bash
PYTHONPATH=packages/quant pytest -q
```

## Live public market data

```env
MARKET_MODE=live
LIVE_VENUES=binance,coinbase
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
```

The runtime stays paper-only. Public market feeds require no trading credentials.

## Safety boundary for future live routing

A live broker must require both:

```env
ENABLE_LIVE_TRADING=true
LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY_IS_AT_RISK
```

The browser must never receive exchange signing keys. All live orders must still pass the central RiskEngine.

## Data flow

```text
Exchange WebSockets / Simulator
              |
        Normalized Quote
              |
          MarketState
              |
      Strategy Detectors
              |
        Opportunity
              |
      Fee/Slippage Model
              |
          RiskEngine
              |
          PaperBroker
              |
        Fill / Portfolio
              |
        API + WebSocket
              |
           Dashboard
```

## Important design choice

LLMs do not belong in the latency-sensitive execution loop. AI belongs above the deterministic core for
research, experiment generation, explanation, anomaly investigation and strategy documentation.

See `docs/` for architecture, production roadmap, operations, security and market API notes.
