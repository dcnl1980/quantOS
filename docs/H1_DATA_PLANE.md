# H1 data plane

## What shipped

- **Shadow execution mode** — observe opportunities and risk decisions without mutating portfolio or sending orders (`EXECUTION_MODE=shadow` or `MARKET_MODE=shadow`).
- **Redpanda/Kafka bus** — non-blocking quote/book producers (`BUS_BACKEND=memory|redpanda|kafka`).
- **ClickHouse archive** — raw tick + book update sink (`ARCHIVE_BACKEND=memory|clickhouse`).
- **L2 order books** — Binance depth adapter with REST snapshot reseeding on sequence gaps.
- **Instrument registry** — canonical symbols, venue listings, market-graph edges.
- **USD/USDT basis** — normalize venue quote currencies before strategy scans.
- **Clock telemetry** — exchange vs receive offset / stale detection (NTP/PTP readiness signal).
- **OpenTelemetry** — spans around consume/scan/execute paths.

## Run

Default stack (memory bus/archive):

```bash
cp .env.example .env
docker compose up --build
```

Full H1 infra:

```bash
docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
```

Shadow on live public feeds:

```bash
MARKET_MODE=shadow docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
```

## Key endpoints

- `GET /api/v1/data-plane`
- `GET /api/v1/orderbooks`
- `GET /api/v1/instruments`
- `GET /api/v1/basis`
- `GET /api/v1/clock`
- `GET /api/v1/shadow-fills`
