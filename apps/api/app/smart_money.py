from __future__ import annotations

from .models import DetectionSnapshot, MarketSnapshot


def detect_smart_money(snapshot: MarketSnapshot) -> DetectionSnapshot:
    candles = snapshot.candles
    if len(candles) < 25:
        return DetectionSnapshot()

    recent = candles[-1]
    previous_window = candles[-21:-1]
    open_price, high, low, close, volume = recent
    prior_high = max(row[1] for row in previous_window)
    prior_low = min(row[2] for row in previous_window)
    average_volume = sum(row[4] for row in previous_window) / len(previous_window)
    body = abs(close - open_price)
    wick_up = high - max(open_price, close)
    wick_down = min(open_price, close) - low
    range_size = max(high - low, 0.0001)
    volume_spike = volume > average_volume * 1.5

    fake_breakout = high > prior_high and close < prior_high
    fake_breakdown = low < prior_low and close > prior_low
    liquidity_sweep = fake_breakout or fake_breakdown
    stop_hunt = volume_spike and (wick_up > body * 1.6 or wick_down > body * 1.6)
    trapped_longs = fake_breakout and close < open_price and wick_up / range_size > 0.35
    trapped_shorts = fake_breakdown and close > open_price and wick_down / range_size > 0.35
    oi_expansion = snapshot.open_interest_change_pct > 0.35
    crowded_longs = snapshot.long_short_ratio > 1.6
    crowded_shorts = snapshot.long_short_ratio < 0.7
    taker_buy_pressure = snapshot.taker_buy_volume_ratio > 0.58 or snapshot.taker_buy_sell_ratio > 1.25
    taker_sell_pressure = snapshot.taker_buy_volume_ratio < 0.42 or snapshot.taker_buy_sell_ratio < 0.8
    older_window = candles[-41:-21] if len(candles) >= 45 else candles[-25:-13]
    recent_high = max(row[1] for row in previous_window)
    recent_low = min(row[2] for row in previous_window)
    older_high = max(row[1] for row in older_window)
    older_low = min(row[2] for row in older_window)
    bullish_market_structure = recent_high > older_high and recent_low > older_low
    bearish_market_structure = recent_high < older_high and recent_low < older_low
    break_of_structure = close > prior_high or close < prior_low
    change_of_character = (bearish_market_structure and close > prior_high) or (bullish_market_structure and close < prior_low)
    bullish_fvg = len(candles) >= 3 and candles[-3][1] < low and close > open_price
    bearish_fvg = len(candles) >= 3 and candles[-3][2] > high and close < open_price
    average_body = sum(abs(row[3] - row[0]) for row in previous_window) / len(previous_window)
    displacement = body > average_body * 1.6 and volume > average_volume * 1.2
    bullish_order_block = displacement and close > open_price and any(row[3] < row[0] for row in candles[-6:-1])
    bearish_order_block = displacement and close < open_price and any(row[3] > row[0] for row in candles[-6:-1])

    return DetectionSnapshot(
        liquidity_sweep=liquidity_sweep,
        stop_hunt=stop_hunt,
        fake_breakout=fake_breakout,
        fake_breakdown=fake_breakdown,
        trapped_longs=trapped_longs,
        trapped_shorts=trapped_shorts,
        oi_expansion=oi_expansion,
        crowded_longs=crowded_longs,
        crowded_shorts=crowded_shorts,
        taker_buy_pressure=taker_buy_pressure,
        taker_sell_pressure=taker_sell_pressure,
        bullish_market_structure=bullish_market_structure,
        bearish_market_structure=bearish_market_structure,
        break_of_structure=break_of_structure,
        change_of_character=change_of_character,
        bullish_fvg=bullish_fvg,
        bearish_fvg=bearish_fvg,
        bullish_order_block=bullish_order_block,
        bearish_order_block=bearish_order_block,
    )
