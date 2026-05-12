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
