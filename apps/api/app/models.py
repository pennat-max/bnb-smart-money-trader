from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SignalType = Literal["LONG", "SHORT", "WAIT", "CANCEL"]


class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    btc_price: float
    funding_rate: float
    open_interest: float
    open_interest_change_pct: float = 0
    long_short_ratio: float = 1
    taker_buy_sell_ratio: float = 1
    taker_buy_volume_ratio: float = 0.5
    candles: list[list[float]]


class IndicatorSnapshot(BaseModel):
    ema5: float
    ema10: float
    ema30: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float


class DetectionSnapshot(BaseModel):
    liquidity_sweep: bool = False
    stop_hunt: bool = False
    fake_breakout: bool = False
    fake_breakdown: bool = False
    trapped_longs: bool = False
    trapped_shorts: bool = False
    oi_expansion: bool = False
    crowded_longs: bool = False
    crowded_shorts: bool = False
    taker_buy_pressure: bool = False
    taker_sell_pressure: bool = False


class TradeSuggestion(BaseModel):
    entry: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    position_size: float = 0


class SignalResponse(BaseModel):
    created_at: datetime
    mode: str = "signal_only"
    symbol: str = "BNBUSDT"
    signal: SignalType
    price: float
    btc_price: float
    funding_rate: float
    open_interest: float
    open_interest_change_pct: float = 0
    long_short_ratio: float = 1
    taker_buy_sell_ratio: float = 1
    taker_buy_volume_ratio: float = 0.5
    indicators: IndicatorSnapshot
    detections: DetectionSnapshot
    reasoning_th: str
    reasoning_en: str
    suggestion: TradeSuggestion
    confidence: int = Field(ge=0, le=100)
    risk_score: int = Field(ge=0, le=100)
    daily_pnl_pct: float
    risk_rules: dict[str, bool | float | int | str]
    active_position: dict[str, str | float | None]
    personality_log: str
    journal_saved: bool = False
    journal_backend: Literal["local", "supabase", "none"] = "none"
    alert_sent: bool = False


class TestnetOrderPreviewRequest(BaseModel):
    symbol: str = "BNBUSDT"
    side: SignalType = "WAIT"
    entry: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    position_size: float = 0
    confidence: int = Field(default=0, ge=0, le=100)


class RuntimeStatus(BaseModel):
    mode: str
    binance_testnet: bool
    real_trading: bool = False
    supabase_configured: bool
    journal_backend: Literal["local", "supabase", "none", "unknown"]
    line_alert_enabled: bool
    line_configured: bool
    paper_trading_enabled: bool
    paper_trading_interval_seconds: int
    risk_daily_target_pct: float
    risk_max_daily_loss_pct: float
    risk_min_confidence: int
    risk_max_active_bnb_positions: int


class DerivativesMetrics(BaseModel):
    symbol: str = "BNBUSDT"
    period: str = "15m"
    source: str = "binance_public_futures"
    data_ok: bool
    open_interest_change_pct: float = 0
    long_short_ratio: float = 1
    long_account: float = 0.5
    short_account: float = 0.5
    taker_buy_sell_ratio: float = 1
    taker_buy_volume_ratio: float = 0.5
    bid_ask_imbalance: float = 0
    smart_money_note: str = ""


class BacktestRequest(BaseModel):
    symbol: str = "BNBUSDT"
    interval: Literal["1m", "5m", "15m", "1h"] = "15m"
    period_days: int = Field(default=7, ge=1, le=30)
    limit: int = Field(default=500, ge=150, le=1500)
    lookahead_candles: int = Field(default=30, ge=3, le=240)
    starting_balance: float = Field(default=1000, gt=0)
    optimize_for_win_rate: bool = True
    smart_money_priority: bool = True
    min_trades: int = Field(default=10, ge=1, le=500)


class BacktestTrade(BaseModel):
    opened_at: int
    closed_at: int
    side: Literal["LONG", "SHORT"]
    entry: float
    take_profit: float
    stop_loss: float
    exit_price: float
    outcome: Literal["WIN", "LOSS", "TIMEOUT"]
    pnl_pct: float
    confidence: int
    reason: str


class BacktestResult(BaseModel):
    symbol: str
    interval: str
    period_days: int
    candles_tested: int
    trades: int
    wins: int
    losses: int
    timeouts: int
    win_rate: float
    total_pnl_pct: float
    ending_balance: float
    max_drawdown_pct: float
    learning_note: str
    profile: str = "base"
    optimizer_note: str = ""
    tested_profiles: list[dict[str, float | int | str]] = []
    recent_trades: list[BacktestTrade]


class PaperRunRequest(BaseModel):
    enabled: bool = True
    balance: float = Field(default=1000, gt=0)
    risk_pct: float = Field(default=1.0, ge=0.1, le=5)
    daily_pnl_pct: float = 0
    active_bnb_positions: int = 0


class PaperTradeRecord(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    symbol: str = "BNBUSDT"
    side: Literal["LONG", "SHORT"]
    status: Literal["OPEN", "CLOSED"]
    entry: float
    take_profit: float
    stop_loss: float
    size: float
    confidence: int
    opened_price: float
    current_price: float
    exit_price: float | None = None
    pnl_pct: float = 0
    pnl_usdt: float = 0
    outcome: Literal["OPEN", "WIN", "LOSS", "MANUAL", "TIMEOUT"] = "OPEN"
    reasoning_th: str = ""


class PaperRunResponse(BaseModel):
    ok: bool
    message: str
    mode: str = "paper_only"
    signal: SignalType
    confidence: int
    price: float
    last_tick_at: datetime
    entry_block_reason: str
    active_trade: PaperTradeRecord | None = None
    closed_trade: PaperTradeRecord | None = None
    learning_summary: dict[str, float | int | str]
