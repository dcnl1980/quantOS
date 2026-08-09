from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Quant OS"
    env: str = "dev"

    # Market data source: simulator | live | shadow
    # shadow is an alias for live feeds + execution_mode=shadow.
    market_mode: str = "simulator"
    # Execution policy: paper | shadow | testnet | live
    execution_mode: str = "paper"
    live_venues: str = "binance,coinbase"
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"
    sim_tick_ms: int = 250
    sim_arbitrage_probability: float = .08

    database_url: str = "postgresql+asyncpg://quant:quant@localhost:5432/quant"
    api_cors_origins: str = "http://localhost:3000"

    initial_cash: float = 100000
    paper_auto_execute: bool = True
    paper_order_notional: float = 1000

    min_net_edge_bps: float = 8
    max_order_notional: float = 2500
    max_symbol_exposure: float = 15000
    max_venue_exposure: float = 30000
    max_daily_loss: float = 3000
    max_drawdown_pct: float = 5
    max_slippage_bps: float = 15
    circuit_breaker_rejections: int = 25

    binance_taker_fee_bps: float = 10
    coinbase_taker_fee_bps: float = 12
    sim_a_taker_fee_bps: float = 5
    sim_b_taker_fee_bps: float = 5
    default_slippage_bps: float = 2

    # python | cpp | rust
    execution_engine: str = "python"
    execution_engine_host: str = "127.0.0.1"
    execution_engine_port: int = 9100
    execution_timeout_ms: int = 1000
    min_execution_interval_ms: int = 250

    enable_live_trading: bool = False
    live_trading_ack: str = ""
    log_level: str = "INFO"

    # H2 execution plane
    testnet_venues: str = "sim_a,sim_b"
    testnet_api_key: str = "testnet"
    testnet_api_secret: str = "testnet"
    testnet_partial_fill_ratio: float = 0.65
    testnet_auto_execute: bool = True
    inventory_venue_weights: str = "sim_a:0.5,sim_b:0.5,binance:0.5,coinbase:0.5"
    recon_interval_sec: float = 1.0
    min_hedge_qty: float = 1e-6
    fee_tier_volume_binance: float = 0
    fee_tier_volume_coinbase: float = 0

    # H1 data plane
    data_plane_enabled: bool = True
    bus_backend: str = "memory"  # memory | kafka | redpanda
    kafka_bootstrap: str = "localhost:19092"
    kafka_quotes_topic: str = "quotes.raw"
    kafka_books_topic: str = "book.deltas"
    archive_backend: str = "memory"  # memory | clickhouse
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_database: str = "quant"
    otel_enabled: bool = True
    enable_l2_books: bool = True
    l2_depth: int = 20
    usdt_usd_basis: float = 1.0
    clock_stale_ms: float = 250.0

    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    def resolved_market_mode(self) -> str:
        mode = self.market_mode.lower().strip()
        if mode == "shadow":
            return "live"
        if mode in {"live", "live-public-data", "live_public_data"}:
            return "live"
        return "simulator"

    def resolved_execution_mode(self) -> str:
        if self.market_mode.lower().strip() == "shadow":
            return "shadow"
        mode = self.execution_mode.lower().strip()
        if mode not in {"paper", "shadow", "testnet", "live"}:
            return "paper"
        return mode

    @property
    def symbol_list(self):
        return [x.strip().upper() for x in self.symbols.split(",") if x.strip()]

    @property
    def venue_list(self):
        return [x.strip().lower() for x in self.live_venues.split(",") if x.strip()]

    @property
    def testnet_venue_list(self):
        return [x.strip().lower() for x in self.testnet_venues.split(",") if x.strip()]

    @property
    def inventory_weights(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for part in self.inventory_venue_weights.split(","):
            if ":" not in part:
                continue
            venue, weight = part.split(":", 1)
            try:
                out[venue.strip().lower()] = float(weight)
            except ValueError:
                continue
        return out

    @property
    def fees(self):
        return {
            "binance": self.binance_taker_fee_bps,
            "coinbase": self.coinbase_taker_fee_bps,
            "sim_a": self.sim_a_taker_fee_bps,
            "sim_b": self.sim_b_taker_fee_bps,
            "binance_testnet": self.binance_taker_fee_bps,
            "coinbase_testnet": self.coinbase_taker_fee_bps,
        }

    @property
    def native_execution(self):
        return self.execution_engine.lower() in {"cpp", "rust"}

    @property
    def sends_orders(self) -> bool:
        mode = self.resolved_execution_mode()
        if mode == "paper":
            return self.paper_auto_execute
        if mode == "testnet":
            return self.testnet_auto_execute
        return False

    @property
    def is_shadow(self) -> bool:
        return self.resolved_execution_mode() == "shadow"

    @property
    def is_testnet(self) -> bool:
        return self.resolved_execution_mode() == "testnet"


settings = Settings()
