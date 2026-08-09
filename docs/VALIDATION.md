# Validation report

Generated product validation performed in the build environment.

## Claim under test

All H0–H5 planes are functionally green locally:
Python core + horizon e2e, C++ engine CTest, Rust unit tests, and native TCP smoke
(`EVAL_ARB` non-mutating, `EXEC_ARB` mutating).

## Python (H0–H5)

Command:

```bash
make e2e-full
# or
PYTHONPATH=packages/quant:services/api pytest -q
```

Result: **49 passed**

Coverage includes:

| Horizon | Surfaces |
|---|---|
| H0 | arbitrage/costs/risk/paper/backtest units; `/`, `/health`, `/ready`, snapshot, quotes, opportunities, portfolio, fills, strategies, risk, engine, backtest, metrics |
| H1 | orderbook/basis/clock/registry units; shadow non-mutation e2e; paper still executes; data-plane bus/archive/telemetry; instruments/basis/clock/orderbooks/shadow-fills |
| H2 | order FSM, fees, inventory, hedge, recon units; testnet gateway e2e; live mode blocked without ack |
| H3 | walk-forward/MC/sensitivity/features/experiments/gates; ResearchLab suite; `/research/*` API |
| H4 | ontology graph edges, prediction complements, contradictions; `/ontology/*` + `/market-graph` |
| H5 | policy refusals, plan/analyze/ask/codegen; `/copilot/*` |
| Full | `tests/test_e2e_full_h0_h5.py` hits every plane in one API session |

Makefile targets: `make e2e`, `e2e-h2`, `e2e-h3`, `e2e-h4`, `e2e-h5`, `e2e-full`, `validate`.

## C++20

Compiler: GCC 14.2 / CMake Release

```bash
make cpp-test
```

- CMake configure: passed
- native binary build: passed
- CTest `engine-tests`: passed

## Rust

```bash
make rust-test
```

- `shadow_evaluate_does_not_mutate`: passed
- `executes_positive_arb_and_rejects_low_edge`: passed

## Native TCP smoke

```bash
make native-smoke
```

Observed:

- `PING` → `{"type":"pong","engine":"cpp20"}`
- `EVAL_ARB` approved with `trade_count` unchanged / cash unchanged on `SNAPSHOT`
- `EXEC_ARB` approved with positive `trade_pnl` and cash mutation
- `RESET` ok

## Environment notes

- Docker Compose H1 overlay (`redpanda` + `clickhouse`) is provided; this validation
  environment may not have a Docker daemon, so Kafka/ClickHouse are exercised via
  in-memory backends (`BUS_BACKEND=memory`, `ARCHIVE_BACKEND=memory`).
- Live capital remains gated (`LiveBroker` / enable+ack / testnet promotion).
- Copilot is advisory-only and refuses risk bypass, live enablement, and signing-key requests.

## Horizon docs

- H1: `docs/H1_DATA_PLANE.md`
- H2: `docs/H2_EXECUTION.md`
- H3: `docs/H3_RESEARCH.md`
- H4: `docs/H4_ONTOLOGY.md`
- H5: `docs/H5_COPILOT.md`
