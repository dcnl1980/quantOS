# Quant OS — Native Execution Edition

Quant OS is a runnable real-time market intelligence and paper-execution product with a web terminal,
live public exchange feeds, cost-aware opportunity detection, deterministic risk controls, backtesting,
PostgreSQL persistence, and **two interchangeable native execution engines**:

- **C++20 engine** — default Docker hot path
- **Rust/Tokio engine** — protocol-compatible alternative

The system is designed so that the AI/research layer never sits inside the latency-sensitive execution loop.

> This repository is a working paper-trading/research product, not a claim of guaranteed profitability.
> Real-money multi-venue arbitrage additionally requires authenticated venue routers, capital pre-positioning,
> partial-fill handling, inventory management, venue-specific precision/filter logic, reconciliation, and
> operational controls. Those boundaries are deliberately explicit rather than silently faked.

## 1. Start the complete product

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- Terminal UI: `http://localhost:3000`
- FastAPI / Swagger: `http://localhost:8000/docs`
- Native engine status: `http://localhost:8000/api/v1/engine`
- Market ontology graph: `http://localhost:8000/api/v1/ontology/graph`
- Ontology contradictions: `http://localhost:8000/api/v1/ontology/scan`

The default configuration uses synthetic multi-venue prices so the complete path is visible immediately:

```text
Simulator
  -> normalized quotes
  -> opportunity detector
  -> fee/slippage model
  -> native C++ risk + execution engine
  -> paired paper fills
  -> portfolio/P&L
  -> Postgres
  -> WebSocket
  -> dashboard
```

## 2. Switch to real public market data

Edit `.env`:

```env
MARKET_MODE=live
LIVE_VENUES=binance,coinbase
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
```

The system consumes public market-data WebSockets while keeping execution in paper mode.

## 3. Shadow mode (observe only)

```bash
MARKET_MODE=shadow docker compose up --build
```

Strategies and risk still run. Hypothetical fills are emitted as `shadow_fill` events. Portfolio cash
and native engine state are not mutated, and no venue orders are sent.

## 3b. H2 testnet execution

```bash
EXECUTION_MODE=testnet TESTNET_VENUES=sim_a,sim_b docker compose up --build
```

Authenticated testnet/simulated venue router with idempotent orders, cancel/replace, partial-fill
hedging, inventory allocation, fee tiers and reconciliation. See `docs/H2_EXECUTION.md`.
Live capital remains gated.

## 4. H1 data plane (Redpanda + ClickHouse)

```bash
docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
```

See `docs/H1_DATA_PLANE.md` for bus/archive/orderbook/basis/telemetry endpoints.

## 5. Use the Rust engine instead

```bash
docker compose -f docker-compose.yml -f docker-compose.rust.yml up --build
```

Both native engines implement the same private TCP execution protocol, so the API, risk telemetry,
strategies and UI do not need to change.

## 6. Native engine responsibilities

The C++/Rust service independently enforces:

- minimum net edge
- maximum order notional
- maximum daily loss
- maximum drawdown
- maximum modeled slippage
- circuit breaker after repeated rejections
- 5% equity cap per opportunity
- cost-aware paired execution
- engine-owned portfolio state
- realized P&L
- turnover
- execution decision latency telemetry

The Python layer cannot bypass those controls by simply constructing a trade request.

## 7. Execution protocol

The API keeps one persistent private TCP connection to the engine.

```text
PING
SNAPSHOT
RESET
RESET_CB

EXEC_ARB|
opportunity_id|
symbol|
buy_venue|
sell_venue|
buy_price|
sell_price|
net_edge_bps|
max_notional|
desired_notional|
buy_fee_bps|
sell_fee_bps|
slippage_bps
```

See `docs/EXECUTION_PROTOCOL.md`.

## 8. Product features

### Market layer
- Binance Spot `bookTicker` public WebSocket
- Coinbase Advanced Trade public ticker WebSocket
- deterministic multi-venue simulator
- normalized quote model
- in-memory rolling quote history
- reconnect/backoff behavior

### Intelligence
- cross-venue arbitrage detector
- fee + slippage-adjusted edge
- lead/lag analysis detector
- opportunity scoring
- market relationship graph endpoint
- strategy registry

### Execution
- C++20 native engine
- Rust/Tokio native engine
- persistent private TCP transport
- second risk gate inside native process
- paired paper execution
- shadow dry-run (`EVAL_ARB` / `EXECUTION_MODE=shadow`)
- testnet gateway (`EXECUTION_MODE=testnet`) with order FSM, hedges, recon
- execution cooldown per route
- fills, realized P&L and turnover
- circuit breaker
- reset/control API

### H1 data plane
- Redpanda/Kafka quote + book bus
- ClickHouse raw tick archive
- Binance L2 books with gap recovery
- instrument registry
- USD/USDT basis normalization
- exchange clock skew telemetry
- OpenTelemetry spans

### Research
- deterministic replay backtester
- synthetic backtest endpoint
- Strategy Factory architecture
- walk-forward validation
- Monte Carlo perturbation
- parameter sensitivity sweeps
- experiment registry + promotion gates
- feature store
- benchmark and smoke-test tools

### Platform
- FastAPI REST
- WebSocket event bus
- Next.js terminal
- PostgreSQL persistence
- Docker Compose (+ H1 overlay)
- Prometheus endpoint
- health/readiness endpoints
- SQL audit schema
- C++ CTest
- Python pytest
- Rust unit tests executed by its Docker build

## 9. Dashboard

The terminal shows:

- portfolio equity
- session P&L and drawdown
- opportunity count
- risk-engine state
- selected native execution engine
- last native decision latency
- real-time market matrix
- cost-adjusted executable edge
- paper execution log
- replay Strategy Lab
- risk guardrails
- live event bus

## 10. Validate the native engine locally

C++:

```bash
./scripts/build_cpp_local.sh
./scripts/run_cpp_local.sh
```

Then:

```bash
python scripts/smoke_native.py
python scripts/benchmark_native.py -n 10000
```

The benchmark reports two different metrics:

1. internal C++ decision time;
2. full local TCP request/response time.

Do not interpret localhost benchmark numbers as exchange execution latency.

## 11. Important architecture boundary

```text
                      RESEARCH / CONTROL PLANE
                      ------------------------
                       AI Quant Copilot
                       Strategy Factory
                       Experiment registry
                              |
                              v
LIVE FEEDS -> NORMALIZER -> STRATEGIES -> OPPORTUNITY
                                         |
                              deterministic request
                                         |
                                         v
                       NATIVE EXECUTION PLANE
                       ----------------------
                         C++20 or Rust
                         risk re-check
                         paper/router boundary
                         fill state
                         portfolio state
                                         |
                                         v
                              AUDIT / METRICS
```

No LLM call is required for a quote, signal, risk decision or execution.

## 12. Production path to real capital

The next step is not “turn on an API key.” A proper authenticated router needs, per venue:

- exchange-info / precision and minimum-notional filters
- authenticated order signing
- idempotent client order IDs
- market/limit/IOC/FOK semantics
- partial fill state machine
- cancel/replace
- user-data/order WebSocket
- local/venue reconciliation
- stale quote rejection
- leg-risk and emergency hedge policy
- per-venue inventory/capital allocator
- fee-tier awareness
- rate-limit handling
- clock synchronization
- kill switch independent from strategy workers
- secret management and key rotation
- testnet/shadow promotion gate

The repository contains the interfaces and operating model for this extension, but deliberately does not
ship a configuration that can accidentally spend real money.

## Repository map

```text
quant-os/
├── apps/web/                       Next.js terminal
├── services/api/                   FastAPI control/data plane
├── services/execution-cpp/         C++20 native execution engine
├── services/execution-rust/        Rust/Tokio native execution engine
├── packages/quant/quant_os/        market/strategy/backtest core
├── infra/postgres/                 persistence bootstrap
├── scripts/                        native build/smoke/benchmark
├── tests/                          Python tests
├── docs/
├── docker-compose.yml
├── docker-compose.rust.yml
└── .env.example
```
