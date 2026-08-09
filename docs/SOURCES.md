# Official API references checked on 2026-08-09

## Binance
Spot WebSocket Market Streams document `wss://stream.binance.com:9443`; `<symbol>@bookTicker` is the real-time
best bid/ask stream.
https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-streams/~

## Coinbase
Advanced Trade public market-data WebSocket:
`wss://advanced-trade-ws.coinbase.com`
https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview

## Polymarket
Public market channel provides Level 2 market/orderbook/price/trade updates. Correct subscriptions require
current asset IDs, so this repository leaves discovery + semantic mapping as an explicit extension rather than
shipping stale hard-coded IDs.
https://docs.polymarket.com/market-data/websocket/market-channel


## Binance Spot Test Network
Official testnet documentation confirms separate Spot Test Network REST/WebSocket facilities and test assets.
`https://developers.binance.com/en/docs/products/spot/testnet/general-info`
`https://developers.binance.com/en/docs/products/spot/testnet/rest-api`
`https://developers.binance.com/en/docs/products/spot/testnet/web-socket-streams`

## Rust runtime libraries
The Rust engine uses Tokio for async TCP. The container builds from the official Rust image and runs Cargo tests
before producing the release binary.
