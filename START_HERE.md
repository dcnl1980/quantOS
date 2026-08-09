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

Read `README.md` and `docs/VALIDATION.md` before enabling any future authenticated venue router.
