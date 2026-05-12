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
    if detections.oi_expansion:
        score += 4
    if detections.crowded_longs or detections.crowded_shorts:
        score += 3
    if detections.taker_buy_pressure or detections.taker_sell_pressure:
        score += 3
    if detections.break_of_structure or detections.change_of_character:
        score += 4
    if detections.bullish_fvg or detections.bearish_fvg:
        score += 3
    if detections.bullish_order_block or detections.bearish_order_block:
        score += 4
    if detections.vwap_reclaim or detections.vwap_rejection:
        score += 3
    if detections.bullish_mtf_alignment or detections.bearish_mtf_alignment:
        score += 6
    if detections.liquidation_long_flush or detections.liquidation_short_flush:
        score += 5
    if detections.bid_wall or detections.ask_wall:
        score += 2
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
    detections = detect_smart_money(snapshot)
    closes = [row[3] for row in snapshot.candles]
    price = snapshot.price
    btc_change = closes[-1] - closes[-8] if len(closes) >= 8 else 0

    bullish_trend = indicators.ema5 > indicators.ema10 > indicators.ema30 and indicators.macd_histogram > 0
    bearish_trend = indicators.ema5 < indicators.ema10 < indicators.ema30 and indicators.macd_histogram < 0
    btc_supports_risk = btc_change >= 0

    signal = "WAIT"
    base_confidence = 52
    bullish_context = detections.bullish_mtf_alignment or detections.discount_zone or detections.vwap_reclaim
    bearish_context = detections.bearish_mtf_alignment or detections.premium_zone or detections.vwap_rejection
    if bullish_trend and detections.trapped_shorts and indicators.rsi < 72 and btc_supports_risk:
        signal = "LONG"
        base_confidence = 62
    elif bearish_trend and detections.trapped_longs and indicators.rsi > 28:
        signal = "SHORT"
        base_confidence = 62
    elif bullish_trend and bullish_context and indicators.rsi < 68 and price > indicators.bb_middle and btc_supports_risk:
        signal = "LONG"
        base_confidence = 58
    elif bearish_trend and bearish_context and indicators.rsi > 32 and price < indicators.bb_middle:
        signal = "SHORT"
        base_confidence = 58

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
    thai_trend = "\u0e02\u0e32\u0e02\u0e36\u0e49\u0e19" if bullish_trend else "\u0e02\u0e32\u0e25\u0e07" if bearish_trend else "\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e0a\u0e31\u0e14"
    reasoning_th = (
        f"BNB \u0e15\u0e2d\u0e19\u0e19\u0e35\u0e49\u0e40\u0e1b\u0e47\u0e19 {signal}. EMA/MACD \u0e43\u0e2b\u0e49\u0e20\u0e32\u0e1e {thai_trend}; "
        f"RSI {indicators.rsi:.1f}. {pattern_text} VWAP {snapshot.vwap:.2f}, MTF {snapshot.mtf_bias}. "
        f"Funding {snapshot.funding_rate:.4%}, OI {snapshot.open_interest:.0f}. "
        "\u0e23\u0e30\u0e1a\u0e1a\u0e22\u0e31\u0e07\u0e40\u0e1b\u0e47\u0e19 signal-only \u0e44\u0e21\u0e48\u0e21\u0e35\u0e01\u0e32\u0e23\u0e2a\u0e48\u0e07\u0e2d\u0e2d\u0e40\u0e14\u0e2d\u0e23\u0e4c\u0e08\u0e23\u0e34\u0e07."
    )
    reasoning_en = (
        f"Signal is {signal}. Trend is {'bullish' if bullish_trend else 'bearish' if bearish_trend else 'mixed'} "
        f"with RSI {indicators.rsi:.1f}, MACD histogram {indicators.macd_histogram:.4f}, "
        f"funding {snapshot.funding_rate:.4%}, and open interest {snapshot.open_interest:.0f}."
    )
    personality_log = _personality_log(signal, confidence, int(risk_score), detections)

    return SignalResponse(
        created_at=datetime.now(timezone.utc),
        mode=settings.app_mode,
        symbol=snapshot.symbol,
        signal=signal,
        price=price,
        btc_price=snapshot.btc_price,
        funding_rate=snapshot.funding_rate,
        open_interest=snapshot.open_interest,
        open_interest_change_pct=snapshot.open_interest_change_pct,
        long_short_ratio=snapshot.long_short_ratio,
        taker_buy_sell_ratio=snapshot.taker_buy_sell_ratio,
        taker_buy_volume_ratio=snapshot.taker_buy_volume_ratio,
        bid_ask_imbalance=snapshot.bid_ask_imbalance,
        depth_wall_side=snapshot.depth_wall_side,
        depth_wall_price=snapshot.depth_wall_price,
        vwap=snapshot.vwap,
        session_high=snapshot.session_high,
        session_low=snapshot.session_low,
        session_position=snapshot.session_position,
        volume_zscore=snapshot.volume_zscore,
        mtf_bias=snapshot.mtf_bias,
        mtf_alignment_score=snapshot.mtf_alignment_score,
        mtf_trends=snapshot.mtf_trends,
        liquidation_imbalance=snapshot.liquidation_imbalance,
        liquidation_spike=snapshot.liquidation_spike,
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
    if detections.oi_expansion:
        names.append("OI expansion")
    if detections.crowded_longs:
        names.append("crowded longs")
    if detections.crowded_shorts:
        names.append("crowded shorts")
    if detections.taker_buy_pressure:
        names.append("taker buy pressure")
    if detections.taker_sell_pressure:
        names.append("taker sell pressure")
    if detections.bullish_market_structure:
        names.append("bullish market structure")
    if detections.bearish_market_structure:
        names.append("bearish market structure")
    if detections.break_of_structure:
        names.append("break of structure")
    if detections.change_of_character:
        names.append("change of character")
    if detections.bullish_fvg:
        names.append("bullish FVG")
    if detections.bearish_fvg:
        names.append("bearish FVG")
    if detections.bullish_order_block:
        names.append("bullish order block")
    if detections.bearish_order_block:
        names.append("bearish order block")
    if detections.vwap_reclaim:
        names.append("VWAP reclaim")
    if detections.vwap_rejection:
        names.append("VWAP rejection")
    if detections.premium_zone:
        names.append("premium zone")
    if detections.discount_zone:
        names.append("discount zone")
    if detections.bullish_mtf_alignment:
        names.append("bullish MTF alignment")
    if detections.bearish_mtf_alignment:
        names.append("bearish MTF alignment")
    if detections.liquidation_long_flush:
        names.append("long liquidation flush")
    if detections.liquidation_short_flush:
        names.append("short liquidation flush")
    if detections.bid_wall:
        names.append("bid wall")
    if detections.ask_wall:
        names.append("ask wall")
    return "\u0e40\u0e08\u0e2d " + ", ".join(names) + "." if names else "\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e40\u0e08\u0e2d smart money trap \u0e0a\u0e31\u0e14\u0e40\u0e08\u0e19."


def _personality_log(signal: str, confidence: int, risk_score: int, detections: DetectionSnapshot) -> str:
    if signal == "CANCEL":
        return "BNB bot: \u0e43\u0e08\u0e40\u0e22\u0e47\u0e19\u0e01\u0e48\u0e2d\u0e19\u0e19\u0e30 \u0e2a\u0e31\u0e0d\u0e0d\u0e32\u0e13\u0e21\u0e35\u0e41\u0e27\u0e27\u0e41\u0e15\u0e48 risk rule \u0e44\u0e21\u0e48\u0e43\u0e2b\u0e49\u0e1c\u0e48\u0e32\u0e19."
    if signal == "WAIT":
        return "BNB bot: \u0e15\u0e25\u0e32\u0e14\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e19\u0e34\u0e48\u0e07\u0e1e\u0e2d \u0e23\u0e2d\u0e43\u0e2b\u0e49 smart money \u0e40\u0e1c\u0e22\u0e21\u0e37\u0e2d\u0e0a\u0e31\u0e14\u0e01\u0e27\u0e48\u0e32\u0e19\u0e35\u0e49."
    if detections.trapped_longs or detections.trapped_shorts:
        return f"BNB bot: \u0e40\u0e2b\u0e47\u0e19 trap \u0e41\u0e25\u0e49\u0e27 {signal} \u0e44\u0e14\u0e49 \u0e41\u0e15\u0e48\u0e04\u0e38\u0e21 risk score {risk_score} \u0e43\u0e2b\u0e49\u0e41\u0e19\u0e48\u0e19."
    return f"BNB bot: {signal} bias \u0e1e\u0e23\u0e49\u0e2d\u0e21 confidence {confidence} \u0e41\u0e15\u0e48\u0e22\u0e31\u0e07\u0e40\u0e1b\u0e47\u0e19\u0e41\u0e04\u0e48 signal-only."
