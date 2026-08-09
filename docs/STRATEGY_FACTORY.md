# Strategy Factory

```text
Hypothesis -> dataset -> candidate -> replay -> walk-forward -> Monte Carlo -> paper -> shadow
           -> deterministic risk/approval gate -> small canary capital -> scale/pause/retire
```

Promotion gates should include minimum sample size, positive net expectancy after costs, max drawdown,
out-of-sample stability, parameter robustness, concentration limits, paper/live tracking error and documented
failure modes.

AI can propose hypotheses, generate experiment configs, explain fills, compare runs and investigate anomalies.
It should not hold venue signing keys or bypass deterministic risk policy.

## Implemented in H3

The research lab (`docs/H3_RESEARCH.md`) implements this path in-process:

- synthetic replay datasets
- walk-forward OOS folds + stability score
- Monte Carlo quote perturbations (p05/ruin/robustness)
- parameter sensitivity sweeps
- feature store for cross-venue research features
- experiment registry with promote/reject
- `PromotionGate` / `StrategyGovernor` enforcing deterministic thresholds

Use `POST /api/v1/research/suite` for an end-to-end candidate evaluation.

## Implemented in H5

The AI Quant Copilot (`docs/H5_COPILOT.md`) assists the factory without execution authority:

- `POST /api/v1/copilot/plan-experiment` — hypothesis → suite steps
- `POST /api/v1/copilot/explain` — strategy narration from metrics/governance
- `POST /api/v1/copilot/analyze` — anomaly review (ontology + risk + dispersion)
- `POST /api/v1/copilot/codegen` — governed research stubs (no keys / no risk bypass)
