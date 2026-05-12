from __future__ import annotations

from .models import DetectionSnapshot


def detect_smart_money(candles: list[list[float]]) -> DetectionSnapshot:
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

    return DetectionSnapshot(
        liquidity_sweep=liquidity_sweep,
        stop_hunt=stop_hunt,
        fake_breakout=fake_breakout,
        fake_breakdown=fake_breakdown,
        trapped_longs=trapped_longs,
        trapped_shorts=trapped_shorts,
    )
