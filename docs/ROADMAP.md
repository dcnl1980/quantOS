# Production roadmap

## H0 included
Live Binance/Coinbase feeds, simulator, normalized market state, arbitrage + lead/lag, cost model, risk,
paper execution, P&L, backtest, persistence, API/WebSocket, dashboard, Docker and tests.

## H1 data plane (implemented)
Shadow execution mode, Redpanda/Kafka bus, ClickHouse raw tick archive, full L2 orderbooks with gap
recovery, clock skew telemetry, instrument registry, USD/USDT basis model, OpenTelemetry spans.
See `docs/H1_DATA_PLANE.md`.

## H2 execution
Venue testnets, authenticated brokers, user/order streams, idempotent order state machine, cancel/replace,
partial-fill hedge policy, inventory allocator, fee tiers and reconciliation.

## H3 research
Walk-forward validation, Monte Carlo perturbation, experiment registry, parameter sensitivity,
feature store, strategy governance and promotion gates.

## H4 market ontology
Instrument/venue/underlying/settlement graph, prediction-market semantics, contradiction detection.

## H5 AI copilot
Strategy explanations, experiment planning, anomaly analysis, natural-language analytics and governed
code generation. No direct bypass of risk or signing-key boundary.
