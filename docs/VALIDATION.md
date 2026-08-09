# Validation report

Generated product validation performed in the build environment.

## Python
- all Python files parsed successfully
- core pytest suite: 5/5 passed

## C++20
Compiler: GCC 14.2
Build type: Release

- CMake configure: passed
- native binary build: passed
- CTest: passed
- TCP PING: passed
- SNAPSHOT: passed
- positive paired paper execution: passed
- portfolio mutation: passed
- RESET: passed
- 2,000-request local benchmark: passed

One observed build-environment run produced approximately:
- internal decision median: ~60 ns
- internal decision p95: ~250 ns
- localhost persistent TCP median RTT: ~0.40 ms
- localhost persistent TCP p95 RTT: ~0.63 ms

These figures are **not exchange latency benchmarks** and should not be used as expected production trading performance.
They measure a tiny in-memory risk/execution calculation and local process-to-process TCP on the build host.

## Rust
The Rust implementation is protocol-compatible in source and contains unit tests. Its Dockerfile runs:

```text
cargo test --release
cargo build --release
```

Local validation for this branch also ran `cargo test --release` including the shadow `EVAL_ARB` non-mutation test.

## Shadow + H1 (this branch)
- Python suite: `make test` (core + H1 units + async e2e) — 15 passed
- C++ CTest including shadow evaluate — passed
- Rust unit tests including shadow evaluate — passed
- FastAPI TestClient e2e (`EXECUTION_MODE=shadow`, simulator feeds): shadow trades > 0, paper trades = 0,
  portfolio equity unchanged, data-plane bus/archive/telemetry populated
- Native TCP smoke: `EVAL_ARB` does not mutate snapshot; `EXEC_ARB` does

Docker Compose H1 overlay (`redpanda` + `clickhouse`) is provided in `docker-compose.h1.yml`; this validation
environment did not have a Docker daemon, so Kafka/ClickHouse were exercised via in-memory backends.

## H2 execution plane
- Order FSM, fee tiers, inventory, hedge policy, reconciler unit tests — passed
- Simulated testnet broker idempotent place/cancel — passed
- Gateway paired testnet trade + recon — passed
- Runtime e2e `EXECUTION_MODE=testnet` — trades/hedges/fills/inventory populated
- Live mode remains blocked without acknowledgement + testnet promotion

## H3 research plane
- Walk-forward / Monte Carlo / sensitivity / feature store / experiment registry unit tests
- Promotion gate pass/fail coverage
- ResearchLab full suite e2e
- FastAPI research endpoints e2e (`/research/*`)
- Run: `make test` / `make e2e-h3`

## H4 market ontology (this branch)
- Graph edge-type coverage (listings, hedges, settlement, complements, detectors)
- Prediction-market complement normalization
- Contradiction detector (complement, dispersion, out-of-range)
- Polymarket ontology bridge ingest
- FastAPI ontology endpoints e2e (`/ontology/*`, `/market-graph`)
- Run: `make test` / `make e2e-h4`
