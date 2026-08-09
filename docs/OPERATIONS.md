# Operations

## Modes
- simulator: synthetic market data + paper fills (`MARKET_MODE=simulator`, `EXECUTION_MODE=paper`)
- live market data: real public WebSockets + paper fills (`MARKET_MODE=live`, `EXECUTION_MODE=paper`)
- shadow: live or simulated markets, full risk decisions, **no orders / no portfolio mutation**
  - `EXECUTION_MODE=shadow`, or `MARKET_MODE=shadow` (forces live feeds + shadow execution)
- testnet: authenticated testnet/simulated venue router with order FSM, hedges, reconciliation
  - `EXECUTION_MODE=testnet` (see `docs/H2_EXECUTION.md`)
- live trading: not implemented by default (`ENABLE_LIVE_TRADING` + acknowledgement + testnet promotion)

## Data plane
- Default compose uses in-memory bus/archive so the product boots without Kafka/ClickHouse.
- H1 overlay: `docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build`
- Inspect: `GET /api/v1/data-plane`, `/api/v1/orderbooks`, `/api/v1/clock`, `/api/v1/basis`

## Alerts
feed disconnect, stale quote, sequence gap, strategy silence, rejection spike, partial fill imbalance,
reconciliation mismatch, drawdown, daily loss, clock drift and persistence lag.

## Research promotion
Candidates should pass `POST /api/v1/research/suite` (walk-forward + Monte Carlo + sensitivity + gates)
before paper/shadow/testnet scale-up. See `docs/H3_RESEARCH.md`.
Ontology scans (`POST /api/v1/ontology/scan`) should be reviewed for settlement/complement contradictions
before promoting prediction-market linked strategies. See `docs/H4_ONTOLOGY.md`.
Copilot advice (`/api/v1/copilot/*`) is advisory only — never treat it as authority to widen risk,
enable live, or handle venue keys. See `docs/H5_COPILOT.md`.

## Deployment order
persistence -> feeds -> freshness checks -> research gates -> strategies observe-only/shadow -> risk -> paper/testnet broker -> reconciliation checks -> UI.
