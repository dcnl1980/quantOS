from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Quant OS"
    env: str = "dev"

    market_mode: str = "simulator"
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

    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    @property
    def symbol_list(self):
        return [x.strip().upper() for x in self.symbols.split(",") if x.strip()]

    @property
    def venue_list(self):
        return [x.strip().lower() for x in self.live_venues.split(",") if x.strip()]

    @property
    def fees(self):
        return {
            "binance": self.binance_taker_fee_bps,
            "coinbase": self.coinbase_taker_fee_bps,
            "sim_a": self.sim_a_taker_fee_bps,
            "sim_b": self.sim_b_taker_fee_bps,
        }

    @property
    def native_execution(self):
        return self.execution_engine.lower() in {"cpp", "rust"}

settings = Settings()
