# H2 execution plane

## What shipped

- **`EXECUTION_MODE=testnet`** — authenticated simulated venue brokers (Binance/Coinbase testnet-shaped; default `sim_a`/`sim_b` for offline)
- **Idempotent order state machine** — `NEW → ACCEPTED → PARTIAL/FILLED` with cancel/replace transitions and client order IDs
- **User/order streams** — in-process venue events published on the API websocket (`user_stream`)
- **Cancel / replace** — `POST /api/v1/orders/{id}/cancel` and `/replace`
- **Partial-fill hedge policy** — cancel balanced residuals or hedge residual inventory
- **Inventory allocator** — per-venue capital weights and reservations
- **Fee tiers** — maker/taker by 30d volume (`GET /api/v1/fee-tiers`)
- **Reconciliation** — local FSM vs venue open-order reports (`GET /api/v1/reconciliation`)
- **Live gate** — still blocked without acknowledgement **and** testnet promotion

## Run

```bash
EXECUTION_MODE=testnet \
TESTNET_VENUES=sim_a,sim_b \
MARKET_MODE=simulator \
docker compose up --build
```

Offline / tests:

```bash
EXECUTION_ENGINE=python EXECUTION_MODE=testnet MARKET_MODE=simulator make test
```

## Key endpoints

- `GET /api/v1/execution-plane`
- `GET /api/v1/orders`
- `POST /api/v1/orders/{client_order_id}/cancel`
- `POST /api/v1/orders/{client_order_id}/replace?price=...&quantity=...`
- `GET /api/v1/inventory`
- `GET /api/v1/fee-tiers`
- `GET /api/v1/reconciliation`

## Live capital

`EXECUTION_MODE=live` alone does **not** enable real money. `LiveBroker` still requires:

1. `ENABLE_LIVE_TRADING=true`
2. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY_IS_AT_RISK`
3. Successful testnet promotion / reconciliation gates
4. Venue-specific signed live adapters (not shipped)
