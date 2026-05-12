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


@lru_cache
def get_settings() -> Settings:
    return Settings()
