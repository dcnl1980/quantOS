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
