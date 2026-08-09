# Architecture

## Design principles

1. Deterministic hot path: ingestion, strategies, risk and routing do not depend on an LLM.
2. Venue adapters emit one normalized Quote model.
3. Risk precedes every execution path.
4. Strategy code is replayable against historical normalized events.
5. Paper-first and shadow-before-live.
6. Browser is control/observability only; secrets stay server-side.
7. Persistence must never block market processing.

## Production target

```text
Venues -> Feed gateways -> Kafka/Redpanda -> Market state / ClickHouse archive
                                      -> Feature workers -> Strategies
                                                         -> Opportunity
                                                         -> Cost model
                                                         -> Risk
                                                         -> Broker/router
                                                         -> Reconciliation
                                                         -> Postgres/Audit
                                                         -> API/WebSocket -> UI
```

The included local runtime intentionally co-locates these functions so the entire system can run on one machine.

## Market graph extension

Model relationships such as `LISTED_ON`, `DERIVED_FROM`, `PRICED_IN`, `HEDGES`, `CORRELATED_WITH`,
`SETTLES_FROM`, `DETECTED_BY` and `CAUSED_BY`. That enables explainable cross-market intelligence without
placing probabilistic AI in the execution loop.
