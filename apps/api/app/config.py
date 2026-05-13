from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_mode: str = Field(default="signal_only", alias="APP_MODE")
    binance_use_testnet: bool = Field(default=True, alias="BINANCE_USE_TESTNET")
    binance_api_key: str | None = Field(default=None, alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(default=None, alias="BINANCE_API_SECRET")
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_key: str | None = Field(default=None, alias="SUPABASE_KEY")
    local_journal_path: str = Field(default="data/signals.jsonl", alias="LOCAL_JOURNAL_PATH")
    line_alert_enabled: bool = Field(default=False, alias="LINE_ALERT_ENABLED")
    line_channel_access_token: str | None = Field(default=None, alias="LINE_CHANNEL_ACCESS_TOKEN")
    line_user_id: str | None = Field(default=None, alias="LINE_USER_ID")
    paper_trading_enabled: bool = Field(default=True, alias="PAPER_TRADING_ENABLED")
    paper_trading_interval_seconds: int = Field(default=60, alias="PAPER_TRADING_INTERVAL_SECONDS")
    paper_starting_balance: float = Field(default=1000, alias="PAPER_STARTING_BALANCE")
    paper_risk_pct: float = Field(default=1.0, alias="PAPER_RISK_PCT")
    market_collector_enabled: bool = Field(default=True, alias="MARKET_COLLECTOR_ENABLED")
    market_collector_interval_seconds: int = Field(default=300, alias="MARKET_COLLECTOR_INTERVAL_SECONDS")
    candle_collector_enabled: bool = Field(default=True, alias="CANDLE_COLLECTOR_ENABLED")
    candle_collector_interval_seconds: int = Field(default=60, alias="CANDLE_COLLECTOR_INTERVAL_SECONDS")
    candle_collector_symbols: str = Field(default="BNBUSDT,BTCUSDT", alias="CANDLE_COLLECTOR_SYMBOLS")
    candle_collector_timeframes: str = Field(default="1m,5m,15m,1h", alias="CANDLE_COLLECTOR_TIMEFRAMES")
    candle_collector_backfill_days: int = Field(default=7, alias="CANDLE_COLLECTOR_BACKFILL_DAYS")
    ai_committee_enabled: bool = Field(default=True, alias="AI_COMMITTEE_ENABLED")
    ai_research_enabled: bool = Field(default=True, alias="AI_RESEARCH_ENABLED")
    ai_auto_strategy_changes: bool = Field(default=False, alias="AI_AUTO_STRATEGY_CHANGES")
    ai_primary_provider: str = Field(default="deepseek", alias="AI_PRIMARY_PROVIDER")
    ai_secondary_provider: str = Field(default="gemini", alias="AI_SECONDARY_PROVIDER")
    ai_fast_provider: str = Field(default="groq", alias="AI_FAST_PROVIDER")
    ai_premium_provider: str = Field(default="openai", alias="AI_PREMIUM_PROVIDER")
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b", alias="GROQ_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.2", alias="OPENAI_MODEL")
    frontend_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        alias="FRONTEND_ORIGINS",
    )
    frontend_origin_regex: str = Field(
        default=r"https://.*\.vercel\.app",
        alias="FRONTEND_ORIGIN_REGEX",
    )
    risk_daily_target_pct: float = Field(default=1.0, alias="RISK_DAILY_TARGET_PCT")
    risk_max_daily_loss_pct: float = Field(default=2.0, alias="RISK_MAX_DAILY_LOSS_PCT")
    risk_min_confidence: int = Field(default=70, alias="RISK_MIN_CONFIDENCE")
    risk_max_active_bnb_positions: int = Field(default=1, alias="RISK_MAX_ACTIVE_BNB_POSITIONS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def futures_base_url(self) -> str:
        if self.binance_use_testnet:
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def active_supabase_key(self) -> str | None:
        return self.supabase_service_role_key or self.supabase_key

    @property
    def line_configured(self) -> bool:
        return bool(self.line_channel_access_token and self.line_user_id)

    @property
    def candle_symbols(self) -> list[str]:
        return [symbol.strip().upper() for symbol in self.candle_collector_symbols.split(",") if symbol.strip()]

    @property
    def candle_timeframes(self) -> list[str]:
        allowed = {"1m", "5m", "15m", "1h"}
        return [timeframe.strip() for timeframe in self.candle_collector_timeframes.split(",") if timeframe.strip() in allowed]


@lru_cache
def get_settings() -> Settings:
    return Settings()
