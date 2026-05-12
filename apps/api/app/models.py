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
    bid_ask_imbalance: float = 0
    depth_bid_qty: float = 0
    depth_ask_qty: float = 0
    depth_wall_side: str = "neutral"
    depth_wall_price: float | None = None
    vwap: float = 0
    session_high: float = 0
    session_low: float = 0
    session_position: float = 0.5
    volume_zscore: float = 0
    mtf_bias: str = "mixed"
    mtf_alignment_score: int = 0
    mtf_trends: dict[str, str] = {}
    liquidation_buy_qty: float = 0
    liquidation_sell_qty: float = 0
    liquidation_imbalance: float = 0
    liquidation_spike: bool = False
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
    bullish_market_structure: bool = False
    bearish_market_structure: bool = False
    break_of_structure: bool = False
    change_of_character: bool = False
    bullish_fvg: bool = False
    bearish_fvg: bool = False
    bullish_order_block: bool = False
    bearish_order_block: bool = False
    vwap_reclaim: bool = False
    vwap_rejection: bool = False
    premium_zone: bool = False
    discount_zone: bool = False
    bullish_mtf_alignment: bool = False
    bearish_mtf_alignment: bool = False
    liquidation_long_flush: bool = False
    liquidation_short_flush: bool = False
    bid_wall: bool = False
    ask_wall: bool = False


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
    bid_ask_imbalance: float = 0
    depth_wall_side: str = "neutral"
    depth_wall_price: float | None = None
    vwap: float = 0
    session_high: float = 0
    session_low: float = 0
    session_position: float = 0.5
    volume_zscore: float = 0
    mtf_bias: str = "mixed"
    mtf_alignment_score: int = 0
    mtf_trends: dict[str, str] = {}
    liquidation_imbalance: float = 0
    liquidation_spike: bool = False
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
    market_collector_enabled: bool
    market_collector_interval_seconds: int
    candle_collector_enabled: bool = False
    candle_collector_interval_seconds: int = 60
    candle_collector_symbols: list[str] = []
    candle_collector_timeframes: list[str] = []
    ai_committee_enabled: bool = False
    ai_providers_configured: list[str] = []
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
    depth_bid_qty: float = 0
    depth_ask_qty: float = 0
    depth_wall_side: str = "neutral"
    depth_wall_price: float | None = None
    liquidation_buy_qty: float = 0
    liquidation_sell_qty: float = 0
    liquidation_imbalance: float = 0
    liquidation_spike: bool = False
    smart_money_note: str = ""


class MarketDataRecord(BaseModel):
    symbol: str = "BNBUSDT"
    price: float
    btc_price: float
    funding_rate: float
    open_interest: float
    open_interest_change_pct: float = 0
    long_short_ratio: float = 1
    taker_buy_sell_ratio: float = 1
    taker_buy_volume_ratio: float = 0.5
    bid_ask_imbalance: float = 0
    liquidation_imbalance: float = 0
    mtf_alignment_score: int = 0
    detections: dict[str, bool] = {}
    market_context: dict[str, float | int | str | bool | None | dict[str, str]] = {}
    source: str = "collector"


class CandleRecord(BaseModel):
    symbol: str
    timeframe: Literal["1m", "5m", "15m", "1h"]
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleBackfillRequest(BaseModel):
    symbol: str = "BNBUSDT"
    timeframe: Literal["1m", "5m", "15m", "1h"] = "15m"
    days: int = Field(default=7, ge=1, le=90)


class CandleBackfillResponse(BaseModel):
    ok: bool
    symbol: str
    timeframe: str
    days: int
    fetched: int
    saved: int
    backend: Literal["supabase", "none"]
    error: str | None = None


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
    fee_bps: float = Field(default=4.0, ge=0, le=50)
    slippage_bps: float = Field(default=2.0, ge=0, le=100)
    walk_forward_splits: int = Field(default=4, ge=1, le=12)


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
    gross_pnl_pct: float = 0
    cost_pct: float = 0
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
    gross_pnl_pct: float = 0
    cost_pct: float = 0
    total_pnl_pct: float
    ending_balance: float
    max_drawdown_pct: float
    walk_forward: list[dict[str, float | int | str]] = []
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


class AIReportRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    include_premium: bool = False


class AIProviderReport(BaseModel):
    provider: str
    model: str
    ok: bool
    skipped: bool = False
    summary: str
    confidence_adjustment: int = 0
    risk_adjustment: str = "keep"
    recommended_filters: list[str] = []
    error: str | None = None


class AICommitteeReport(BaseModel):
    created_at: datetime
    mode: str = "paper_only_analysis"
    hours: int
    providers_used: list[str]
    providers_skipped: list[str]
    consensus_score: int = Field(ge=0, le=100)
    paper_pnl_pct: float
    estimated_pnl_usdt: float
    win_rate: float
    samples: int
    daily_target_pct: float
    target_status: str
    consensus_summary_th: str
    lessons_learned: list[str]
    strategy_adjustments: list[str]
    safety_notes: list[str]
    provider_reports: list[AIProviderReport]
