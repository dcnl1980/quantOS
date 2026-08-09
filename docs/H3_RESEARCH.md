# H3 research plane

## What shipped

- **Walk-forward validation** — rolling train/test folds with OOS PnL and stability score
- **Monte Carlo perturbation** — quote-path noise, dislocation shocks, dropouts; p05/p50/p95 + ruin rate
- **Parameter sensitivity** — sweeps (e.g. `min_net_edge_bps`) with robustness score
- **Feature store** — in-process cross-venue features (`mid_dispersion_bps`, `cross_venue_gross_bps`, …)
- **Experiment registry** — create/complete/promote/reject experiment records
- **Promotion gates** — deterministic Strategy Factory gates (sample size, expectancy, drawdown, OOS stability, MC robustness, sensitivity)

AI remains outside the hot path: research metrics can inform promotion, but cannot bypass risk or hold venue keys.

## Run

```bash
# Full suite
curl -X POST 'http://localhost:8000/api/v1/research/suite?ticks=2400&mc_runs=30&seed=7'

# Individual studies
curl -X POST 'http://localhost:8000/api/v1/research/walk-forward'
curl -X POST 'http://localhost:8000/api/v1/research/monte-carlo'
curl -X POST 'http://localhost:8000/api/v1/research/sensitivity?parameter=min_net_edge_bps'
```

## Key endpoints

- `GET /api/v1/research`
- `POST /api/v1/research/walk-forward`
- `POST /api/v1/research/monte-carlo`
- `POST /api/v1/research/sensitivity`
- `POST /api/v1/research/suite`
- `GET /api/v1/research/experiments`
- `GET /api/v1/research/experiments/{id}`
- `POST /api/v1/research/promote/{id}`
- `GET /api/v1/research/features`
- `GET /api/v1/research/governance`

## Promotion path

```text
hypothesis -> dataset -> walk-forward -> Monte Carlo -> sensitivity
          -> promotion gate -> paper/shadow/testnet (never live bypass)
```
