from __future__ import annotations

from statistics import fmean, pstdev

from .models import IndicatorSnapshot


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return values[-1]
    multiplier = 2 / (period + 1)
    current = fmean(values[:period])
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    average_gain = fmean(gains) if gains else 0
    average_loss = fmean(losses) if losses else 0
    if average_loss == 0:
        return 100
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def macd(values: list[float]) -> tuple[float, float, float]:
    macd_line = ema(values, 12) - ema(values, 26)
    recent_macd_values = []
    for index in range(max(26, len(values) - 35), len(values) + 1):
        chunk = values[:index]
        if len(chunk) >= 26:
            recent_macd_values.append(ema(chunk, 12) - ema(chunk, 26))
    signal_line = ema(recent_macd_values or [macd_line], 9)
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(values: list[float], period: int = 20, deviations: float = 2) -> tuple[float, float, float]:
    window = values[-period:] if len(values) >= period else values
    middle = fmean(window)
    sigma = pstdev(window) if len(window) > 1 else 0
    return middle + deviations * sigma, middle, middle - deviations * sigma


def calculate_indicators(candles: list[list[float]]) -> IndicatorSnapshot:
    closes = [row[3] for row in candles]
    macd_line, macd_signal, macd_histogram = macd(closes)
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes)
    return IndicatorSnapshot(
        ema5=ema(closes, 5),
        ema10=ema(closes, 10),
        ema30=ema(closes, 30),
        rsi=rsi(closes),
        macd=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
    )
