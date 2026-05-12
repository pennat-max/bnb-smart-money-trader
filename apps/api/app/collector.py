from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from .config import Settings
from .models import MarketDataRecord, SignalResponse

logger = logging.getLogger(__name__)


def market_data_path(settings: Settings) -> Path:
    base = Path(settings.local_journal_path)
    return base.with_name("market_snapshots.jsonl")


def market_record_from_signal(signal: SignalResponse) -> MarketDataRecord:
    return MarketDataRecord(
        symbol=signal.symbol,
        price=signal.price,
        btc_price=signal.btc_price,
        funding_rate=signal.funding_rate,
        open_interest=signal.open_interest,
        open_interest_change_pct=signal.open_interest_change_pct,
        long_short_ratio=signal.long_short_ratio,
        taker_buy_sell_ratio=signal.taker_buy_sell_ratio,
        taker_buy_volume_ratio=signal.taker_buy_volume_ratio,
        bid_ask_imbalance=signal.bid_ask_imbalance,
        liquidation_imbalance=signal.liquidation_imbalance,
        mtf_alignment_score=signal.mtf_alignment_score,
        detections=signal.detections.model_dump(mode="json"),
        market_context={
            "vwap": signal.vwap,
            "session_high": signal.session_high,
            "session_low": signal.session_low,
            "session_position": signal.session_position,
            "volume_zscore": signal.volume_zscore,
            "mtf_bias": signal.mtf_bias,
            "mtf_trends": signal.mtf_trends,
            "depth_wall_side": signal.depth_wall_side,
            "depth_wall_price": signal.depth_wall_price,
            "liquidation_spike": signal.liquidation_spike,
        },
        source="signal_collector",
    )


def save_market_data(settings: Settings, record: MarketDataRecord) -> str:
    if save_market_data_supabase(settings, record):
        return "supabase"
    if save_market_data_local(settings, record):
        return "local"
    return "none"


def supabase_rest_headers(settings: Settings) -> dict[str, str] | None:
    key = settings.active_supabase_key
    if not settings.supabase_url or not key:
        return None
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_publishable_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def save_market_data_supabase(settings: Settings, record: MarketDataRecord) -> bool:
    headers = supabase_rest_headers(settings)
    if headers is None or not settings.supabase_url:
        return False
    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/market_snapshots"
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=record.model_dump(mode="json"), headers={**headers, "Prefer": "return=minimal"})
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("Supabase market snapshot insert failed")
        return False


def save_market_data_local(settings: Settings, record: MarketDataRecord) -> bool:
    try:
        path = market_data_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return True
    except Exception:
        logger.exception("Local market snapshot write failed")
        return False
