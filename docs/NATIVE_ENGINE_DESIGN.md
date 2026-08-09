# Native engine design

## Why a separate process

A separate native process creates a hard boundary between strategy/research code and capital state.
It also allows the hot path to be rewritten, benchmarked, pinned to CPUs, or deployed beside venue gateways
without coupling the web/API stack to native memory layout.

## Current hot path

```text
Opportunity
   |
persistent TCP
   |
parse fixed field protocol
   |
native risk checks
   |
notional sizing
   |
simulated buy/sell prices
   |
fee calculation
   |
paired P&L
   |
portfolio mutation
   |
JSON response
```

## Performance evolution

For lower-latency deployments, replace the private TCP transport with one of:
- Unix domain sockets on one host;
- shared-memory SPSC/MPSC ring buffers;
- Aeron/UDP for dedicated service topologies;
- direct in-process native strategy + router where isolation is less important.

The current TCP transport is deliberately easy to inspect and debug while still keeping the execution calculation native.

## Recommended production threading

- one feed thread/core per critical venue
- instrument partitioning
- one deterministic strategy worker per partition
- one risk/account state owner
- one order-entry session per venue
- reconciliation consumer separated from signal generation
- bounded lock-free queues where measured and justified
- no blocking database/network calls on the decision thread
