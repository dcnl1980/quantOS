# Native Execution Engine Protocol

The API and both native engines use a deliberately tiny line-oriented protocol over a private TCP connection.
The hot-path process does not parse HTTP, allocate large JSON request trees, or invoke an LLM.

## Commands

### Health
`PING`

Response:
```json
{"type":"pong","engine":"cpp20"}
```

### Portfolio
`SNAPSHOT`

### Reset paper state
`RESET`

### Execute a paired cross-venue paper opportunity

```text
EXEC_ARB|
opportunity_id|
symbol|
buy_venue|
sell_venue|
buy_price|
sell_price|
net_edge_bps|
max_notional|
desired_notional|
buy_fee_bps|
sell_fee_bps|
slippage_bps
```

All fields are sent on one physical line, separated by `|`.

Example:

```text
EXEC_ARB|abc|BTCUSDT|binance|coinbase|118000|118400|20|5000|1000|10|12|2
```

The engine independently applies its own risk controls, calculates the actual simulated execution prices,
fees and paired P&L, mutates portfolio state and returns a JSON result.

### Shadow / dry-run evaluate (no portfolio mutation)

Same payload with `EVAL_ARB` instead of `EXEC_ARB`:

```text
EVAL_ARB|abc|BTCUSDT|binance|coinbase|118000|118400|20|5000|1000|10|12|2
```

Returns the same execution JSON shape (`reason` is `shadow_approved` when allowed) but does **not**
mutate cash, trade count, turnover, or circuit-breaker rejection counters.

## Why the engine re-checks risk

The Python strategy layer calculates expected edge, but the native engine is a second trust boundary.
A caller cannot bypass minimum edge, slippage, drawdown, daily-loss, per-order notional or circuit-breaker controls
merely by constructing an API request.

## Live execution boundary

This protocol currently provides deterministic paper execution. A real venue router should be a sibling module
inside the native process, behind the exact same risk gate. Do not let the web application or AI copilot call
exchange signing functions directly.
