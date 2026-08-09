# Start Here

## Default: C++20 native execution

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:3000`.

## Rust native execution

```bash
docker compose -f docker-compose.yml -f docker-compose.rust.yml up --build
```

## C++ engine only

```bash
./scripts/build_cpp_local.sh
./scripts/run_cpp_local.sh
python scripts/smoke_native.py
```

## Live public prices, still paper execution

Set:

```env
MARKET_MODE=live
LIVE_VENUES=binance,coinbase
```

Then restart.

## Shadow mode (observe only, no orders)

```env
MARKET_MODE=shadow
```

or:

```env
MARKET_MODE=live
EXECUTION_MODE=shadow
```

## H1 data plane (Redpanda + ClickHouse)

```bash
docker compose -f docker-compose.yml -f docker-compose.h1.yml up --build
```

See `docs/H1_DATA_PLANE.md`.

Read `README.md` and `docs/VALIDATION.md` before enabling any future authenticated venue router.
