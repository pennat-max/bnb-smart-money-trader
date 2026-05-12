from __future__ import annotations

from datetime import datetime, timezone

from .config import Settings
from .indicators import calculate_indicators
from .models import DetectionSnapshot, MarketSnapshot, SignalResponse, TradeSuggestion
from .risk import evaluate_risk_rules, should_cancel
from .smart_money import detect_smart_money


def _round_price(value: float) -> float:
    return round(value, 2)


def _confidence(base: int, detections: DetectionSnapshot, trend_aligned: bool) -> int:
    score = base
    if detections.liquidity_sweep:
        score += 8
    if detections.stop_hunt:
        score += 6
    if detections.trapped_longs or detections.trapped_shorts:
        score += 7
    if trend_aligned:
        score += 8
    return max(0, min(score, 95))


def generate_signal(
    snapshot: MarketSnapshot,
    settings: Settings,
    daily_pnl_pct: float = 0,
    active_bnb_positions: int = 0,
) -> SignalResponse:
    indicators = calculate_indicators(snapshot.candles)
    detections = detect_smart_money(snapshot.candles)
    closes = [row[3] for row in snapshot.candles]
    price = snapshot.price
    btc_change = closes[-1] - closes[-8] if len(closes) >= 8 else 0

    bullish_trend = indicators.ema5 > indicators.ema10 > indicators.ema30 and indicators.macd_histogram > 0
    bearish_trend = indicators.ema5 < indicators.ema10 < indicators.ema30 and indicators.macd_histogram < 0
    btc_supports_risk = btc_change >= 0

    signal = "WAIT"
    base_confidence = 52
    if bullish_trend and detections.trapped_shorts and indicators.rsi < 72 and btc_supports_risk:
        signal = "LONG"
        base_confidence = 62
    elif bearish_trend and detections.trapped_longs and indicators.rsi > 28:
        signal = "SHORT"
        base_confidence = 62
    elif bullish_trend and indicators.rsi < 68 and price > indicators.bb_middle and btc_supports_risk:
        signal = "LONG"
        base_confidence = 56
    elif bearish_trend and indicators.rsi > 32 and price < indicators.bb_middle:
        signal = "SHORT"
        base_confidence = 56

    trend_aligned = (signal == "LONG" and bullish_trend) or (signal == "SHORT" and bearish_trend)
    confidence = _confidence(base_confidence, detections, trend_aligned) if signal != "WAIT" else 45
    risk_score = max(5, min(100, 100 - confidence + abs(snapshot.funding_rate) * 10000))

    rules = evaluate_risk_rules(settings, confidence, daily_pnl_pct, active_bnb_positions)
    if signal in {"LONG", "SHORT"} and should_cancel(rules):
        signal = "CANCEL"

    stop_distance = max(abs(price - indicators.bb_middle), price * 0.006)
    if signal == "LONG":
        suggestion = TradeSuggestion(
            entry=_round_price(price),
            take_profit=_round_price(price + stop_distance * 1.8),
            stop_loss=_round_price(price - stop_distance),
            position_size=round(max(0, min(1, confidence / 100)) * 0.25, 3),
        )
    elif signal == "SHORT":
        suggestion = TradeSuggestion(
            entry=_round_price(price),
            take_profit=_round_price(price - stop_distance * 1.8),
            stop_loss=_round_price(price + stop_distance),
            position_size=round(max(0, min(1, confidence / 100)) * 0.25, 3),
        )
    else:
        suggestion = TradeSuggestion()

    pattern_text = _pattern_text(detections)
    reasoning_th = (
        f"BNB ตอนนี้เป็น {signal}. EMA/MACD ให้ภาพ {'ขาขึ้น' if bullish_trend else 'ขาลง' if bearish_trend else 'ยังไม่ชัด'}; "
        f"RSI {indicators.rsi:.1f}. {pattern_text} Funding {snapshot.funding_rate:.4%}, OI {snapshot.open_interest:.0f}. "
        "ระบบยังเป็น signal-only ไม่มีการส่งออเดอร์จริง."
    )
    reasoning_en = (
        f"Signal is {signal}. Trend is {'bullish' if bullish_trend else 'bearish' if bearish_trend else 'mixed'} "
        f"with RSI {indicators.rsi:.1f}, MACD histogram {indicators.macd_histogram:.4f}, "
        f"funding {snapshot.funding_rate:.4%}, and open interest {snapshot.open_interest:.0f}."
    )
    personality_log = _personality_log(signal, confidence, risk_score, detections)

    return SignalResponse(
        created_at=datetime.now(timezone.utc),
        mode=settings.app_mode,
        symbol=snapshot.symbol,
        signal=signal,
        price=price,
        btc_price=snapshot.btc_price,
        funding_rate=snapshot.funding_rate,
        open_interest=snapshot.open_interest,
        indicators=indicators,
        detections=detections,
        reasoning_th=reasoning_th,
        reasoning_en=reasoning_en,
        suggestion=suggestion,
        confidence=confidence,
        risk_score=int(risk_score),
        daily_pnl_pct=daily_pnl_pct,
        risk_rules=rules,
        active_position={"symbol": "BNBUSDT", "side": None, "size": 0},
        personality_log=personality_log,
    )


def _pattern_text(detections: DetectionSnapshot) -> str:
    names = []
    if detections.liquidity_sweep:
        names.append("liquidity sweep")
    if detections.stop_hunt:
        names.append("stop hunt")
    if detections.fake_breakout:
        names.append("fake breakout")
    if detections.fake_breakdown:
        names.append("fake breakdown")
    if detections.trapped_longs:
        names.append("trapped longs")
    if detections.trapped_shorts:
        names.append("trapped shorts")
    return "เจอ " + ", ".join(names) + "." if names else "ยังไม่เจอ smart money trap ชัดเจน."


def _personality_log(signal: str, confidence: int, risk_score: int, detections: DetectionSnapshot) -> str:
    if signal == "CANCEL":
        return "BNB bot: ใจเย็นก่อนนะ สัญญาณมีแววแต่ risk rule ไม่ให้ผ่าน."
    if signal == "WAIT":
        return "BNB bot: ตลาดยังไม่นิ่งพอ รอให้ smart money เผยมือชัดกว่านี้."
    if detections.trapped_longs or detections.trapped_shorts:
        return f"BNB bot: เห็น trap แล้ว {signal} ได้ แต่คุม risk score {risk_score} ให้แน่น."
    return f"BNB bot: {signal} bias พร้อม confidence {confidence} แต่ยังเป็นแค่ signal-only."
