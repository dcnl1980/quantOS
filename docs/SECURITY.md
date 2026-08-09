# Security

- Never expose venue credentials to the browser.
- Prefer API keys with withdrawals disabled and IP restrictions.
- Keep separate keys for dev/test/prod.
- Use a secret manager and audited rotation.
- Require two-person production enablement for real capital.
- Add stale-data, sequence-gap, clock-drift and price-collar guards.
- Add cancel-on-disconnect, partial-fill hedging and reconciliation before live use.
- Maintain an immutable audit log.
- Keep a manual kill switch independent of strategy workers.

A future live adapter must require:
`ENABLE_LIVE_TRADING=true` and
`LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY_IS_AT_RISK`.
