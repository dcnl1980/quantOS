# Operations

## Modes
- simulator: synthetic market data + paper fills
- live market data: real public WebSockets + paper fills
- shadow: recommended next step; observe real markets/order states but send no orders
- live: not implemented by default

## Alerts
feed disconnect, stale quote, sequence gap, strategy silence, rejection spike, partial fill imbalance,
reconciliation mismatch, drawdown, daily loss, clock drift and persistence lag.

## Deployment order
persistence -> feeds -> freshness checks -> strategies observe-only -> risk -> paper broker -> reconciliation checks -> UI.
