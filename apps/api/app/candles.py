from __future__ import annotations

import asyncio
import logging
from typing import Literal, cast

import httpx

from .binance_client import BinanceFuturesClient
from .collector import supabase_rest_headers
from .config import Settings
from .models import CandleRecord

logger = logging.getLogger(__name__)

SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h"}


def candle_record(symbol: str, timeframe: str, row: dict) -> dict:
    return CandleRecord(
        symbol=symbol.upper(),
        timeframe=cast(Literal["1m", "5m", "15m", "1h"], timeframe),
        open_time=int(row["open_time"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    ).model_dump(mode="json")


def supabase_candles_url(settings: Settings) -> str | None:
    if not settings.supabase_url:
        return None
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/candles"


def save_candles_supabase(settings: Settings, candles: list[dict], chunk_size: int = 500) -> int:
    if not candles:
        return 0
    headers = supabase_rest_headers(settings)
    url = supabase_candles_url(settings)
    if headers is None or url is None:
        return 0

    saved = 0
    upsert_url = f"{url}?on_conflict=symbol,timeframe,open_time"
    upsert_headers = {
        **headers,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        with httpx.Client(timeout=20) as client:
            for index in range(0, len(candles), chunk_size):
                chunk = candles[index : index + chunk_size]
                response = client.post(upsert_url, json=chunk, headers=upsert_headers)
                response.raise_for_status()
                saved += len(chunk)
        return saved
    except Exception:
        logger.exception("Supabase candle upsert failed")
        return saved


async def backfill_candles(
    settings: Settings,
    client: BinanceFuturesClient,
    symbol: str,
    timeframe: str,
    days: int,
) -> tuple[int, int]:
    validate_timeframe(timeframe)
    candles = await client.raw_market_klines_for_days(symbol.upper(), interval=timeframe, days=days)
    records = [candle_record(symbol, timeframe, row) for row in candles]
    saved = save_candles_supabase(settings, records)
    return len(records), saved


async def collect_recent_candles(
    settings: Settings,
    client: BinanceFuturesClient,
    symbol: str,
    timeframe: str,
    limit: int = 3,
) -> int:
    validate_timeframe(timeframe)
    rows = await client.raw_market_klines_range(symbol.upper(), interval=timeframe, limit=limit)
    records = [candle_record(symbol, timeframe, row) for row in rows]
    return save_candles_supabase(settings, records)


async def collect_all_recent_candles(settings: Settings, client: BinanceFuturesClient) -> dict[str, int]:
    results: dict[str, int] = {}
    for symbol in settings.candle_symbols:
        for timeframe in settings.candle_timeframes:
            key = f"{symbol}:{timeframe}"
            try:
                results[key] = await collect_recent_candles(settings, client, symbol, timeframe)
                await asyncio.sleep(0.05)
            except Exception:
                logger.exception("Recent candle collection failed for %s", key)
                results[key] = 0
    return results


async def initial_candle_backfill(settings: Settings, client: BinanceFuturesClient) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for symbol in settings.candle_symbols:
        for timeframe in settings.candle_timeframes:
            key = f"{symbol}:{timeframe}"
            try:
                fetched, saved = await backfill_candles(
                    settings,
                    client,
                    symbol,
                    timeframe,
                    days=max(1, settings.candle_collector_backfill_days),
                )
                results[key] = {"fetched": fetched, "saved": saved}
                await asyncio.sleep(0.1)
            except Exception:
                logger.exception("Initial candle backfill failed for %s", key)
                results[key] = {"fetched": 0, "saved": 0}
    return results


def validate_timeframe(timeframe: str) -> None:
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
