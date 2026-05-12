from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from .binance_client import interval_to_ms
from .collector import supabase_rest_headers
from .config import Settings

logger = logging.getLogger(__name__)


def supabase_table_url(settings: Settings, table: str) -> str | None:
    if not settings.supabase_url:
        return None
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def log_collector_run(
    settings: Settings,
    *,
    collector: str,
    status: str,
    symbol: str | None = None,
    timeframe: str | None = None,
    rows_fetched: int = 0,
    rows_saved: int = 0,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    headers = supabase_rest_headers(settings)
    url = supabase_table_url(settings, "collector_runs")
    if headers is None or url is None:
        return False

    started = started_at or datetime.now(timezone.utc)
    finished = finished_at or datetime.now(timezone.utc)
    payload = {
        "collector": collector,
        "status": status,
        "symbol": symbol.upper() if symbol else None,
        "timeframe": timeframe,
        "rows_fetched": rows_fetched,
        "rows_saved": rows_saved,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
        "error": error,
        "metadata": metadata or {},
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload, headers={**headers, "Prefer": "return=minimal"})
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("Supabase collector run insert failed")
        return False


def market_data_health(settings: Settings, recent_limit: int = 500) -> dict:
    symbols = settings.candle_symbols or ["BNBUSDT", "BTCUSDT"]
    timeframes = settings.candle_timeframes or ["1m", "5m", "15m", "1h"]
    candle_checks = []
    for symbol in symbols:
        for timeframe in timeframes:
            candle_checks.append(candle_health(settings, symbol, timeframe, recent_limit=recent_limit))

    last_runs = fetch_recent_collector_runs(settings, limit=20)
    statuses = [item["status"] for item in candle_checks]
    overall_status = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return {
        "ok": overall_status != "fail",
        "status": overall_status,
        "symbols": symbols,
        "timeframes": timeframes,
        "candles": candle_checks,
        "collector_runs": last_runs,
        "notes": [
            "Research-only market data health check.",
            "No trading signals or orders are changed by this endpoint.",
        ],
    }


def candle_health(settings: Settings, symbol: str, timeframe: str, recent_limit: int = 500) -> dict:
    count, latest, rows, error = fetch_candle_sample(settings, symbol, timeframe, recent_limit)
    if error:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "status": "fail",
            "count": 0,
            "latest_open_time": None,
            "latest_close_time": None,
            "latest_age_seconds": None,
            "gap_count_recent": 0,
            "error": error,
        }

    gap_count = count_recent_gaps(rows, timeframe)
    latest_age = latest_age_seconds(latest)
    max_age = max(180, int(interval_to_ms(timeframe) / 1000) * 3)
    status = "pass"
    if count == 0:
        status = "fail"
    elif gap_count > 0 or (latest_age is not None and latest_age > max_age):
        status = "warn"

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "status": status,
        "count": count,
        "latest_open_time": latest.get("open_time") if latest else None,
        "latest_close_time": latest.get("close_time") if latest else None,
        "latest_age_seconds": latest_age,
        "gap_count_recent": gap_count,
        "recent_sample_size": len(rows),
        "error": None,
    }


def fetch_candle_sample(settings: Settings, symbol: str, timeframe: str, limit: int) -> tuple[int, dict | None, list[dict], str | None]:
    headers = supabase_rest_headers(settings)
    url = supabase_table_url(settings, "candles")
    if headers is None or url is None:
        return 0, None, [], "Supabase is not configured."

    params = {
        "symbol": f"eq.{symbol.upper()}",
        "timeframe": f"eq.{timeframe}",
        "select": "open_time,close_time",
        "order": "open_time.desc",
        "limit": str(max(1, min(limit, 1000))),
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params, headers={**headers, "Prefer": "count=exact"})
            response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            rows = []
        return parse_supabase_count(response.headers.get("content-range", "")), rows[0] if rows else None, rows, None
    except Exception as exc:
        logger.exception("Supabase candle sample fetch failed")
        return 0, None, [], str(exc)


def fetch_recent_collector_runs(settings: Settings, limit: int = 20) -> list[dict]:
    headers = supabase_rest_headers(settings)
    url = supabase_table_url(settings, "collector_runs")
    if headers is None or url is None:
        return []

    params = {
        "select": "created_at,collector,status,symbol,timeframe,rows_fetched,rows_saved,duration_ms,error",
        "order": "created_at.desc",
        "limit": str(max(1, min(limit, 100))),
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, list) else []
    except Exception:
        logger.exception("Supabase collector run fetch failed")
        return []


def count_recent_gaps(rows_desc: list[dict], timeframe: str) -> int:
    if len(rows_desc) < 2:
        return 0
    interval = interval_to_ms(timeframe)
    rows = list(reversed(rows_desc))
    gaps = 0
    for previous, current in zip(rows, rows[1:]):
        expected = int(previous["open_time"]) + interval
        if int(current["open_time"]) != expected:
            gaps += 1
    return gaps


def latest_age_seconds(latest: dict | None) -> int | None:
    if not latest:
        return None
    timestamp = latest.get("close_time") or latest.get("open_time")
    if timestamp is None:
        return None
    return max(0, int((datetime.now(timezone.utc).timestamp() * 1000 - int(timestamp)) / 1000))


def parse_supabase_count(content_range: str) -> int:
    if "/" not in content_range:
        return 0
    _, total = content_range.rsplit("/", 1)
    if total == "*":
        return 0
    try:
        return int(total)
    except ValueError:
        return 0
