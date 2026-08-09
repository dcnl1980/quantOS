# Production roadmap

## H0 included
Live Binance/Coinbase feeds, simulator, normalized market state, arbitrage + lead/lag, cost model, risk,
paper execution, P&L, backtest, persistence, API/WebSocket, dashboard, Docker and tests.

## H1 data plane (implemented)
Shadow execution mode, Redpanda/Kafka bus, ClickHouse raw tick archive, full L2 orderbooks with gap
recovery, clock skew telemetry, instrument registry, USD/USDT basis model, OpenTelemetry spans.
See `docs/H1_DATA_PLANE.md`.

## H2 execution (implemented)
Venue testnet brokers, authenticated gateway, user/order streams, idempotent order state machine,
cancel/replace, partial-fill hedge policy, inventory allocator, fee tiers and reconciliation.
See `docs/H2_EXECUTION.md`.

## H3 research (implemented)
Walk-forward validation, Monte Carlo perturbation, experiment registry, parameter sensitivity,
feature store, strategy governance and promotion gates.
See `docs/H3_RESEARCH.md`.

## H4 market ontology (implemented)
Instrument/venue/underlying/settlement graph, prediction-market semantics, contradiction detection.
See `docs/H4_ONTOLOGY.md`.

## H5 AI copilot
Strategy explanations, experiment planning, anomaly analysis, natural-language analytics and governed
code generation. No direct bypass of risk or signing-key boundary.
