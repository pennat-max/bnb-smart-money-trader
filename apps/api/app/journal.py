from __future__ import annotations

import json
import logging
from pathlib import Path

from supabase import Client, create_client

from .config import Settings
from .models import SignalResponse

logger = logging.getLogger(__name__)


def get_supabase(settings: Settings) -> Client | None:
    if not settings.supabase_url or not settings.active_supabase_key:
        return None
    try:
        return create_client(settings.supabase_url, settings.active_supabase_key)
    except Exception:
        logger.exception("Supabase client initialization failed")
        return None


def save_signal(settings: Settings, signal: SignalResponse) -> str:
    client = get_supabase(settings)
    if client is None:
        return "local" if save_signal_local(settings, signal) else "none"

    payload = signal.model_dump(mode="json")
    try:
        client.table("trade_signals").insert(
            {
                "symbol": signal.symbol,
                "mode": signal.mode,
                "signal": signal.signal,
                "confidence": signal.confidence,
                "risk_score": signal.risk_score,
                "price": signal.price,
                "btc_price": signal.btc_price,
                "entry": signal.suggestion.entry,
                "take_profit": signal.suggestion.take_profit,
                "stop_loss": signal.suggestion.stop_loss,
                "position_size": signal.suggestion.position_size,
                "daily_pnl_pct": signal.daily_pnl_pct,
                "indicators": signal.indicators.model_dump(mode="json"),
                "detections": signal.detections.model_dump(mode="json"),
                "reasoning_th": signal.reasoning_th,
                "reasoning_en": signal.reasoning_en,
                "personality_log": signal.personality_log,
                "raw_payload": payload,
            }
        ).execute()
        return "supabase"
    except Exception:
        logger.exception("Supabase signal insert failed")
        return "local" if save_signal_local(settings, signal) else "none"


def recent_signals(settings: Settings, limit: int = 25) -> list[dict]:
    client = get_supabase(settings)
    if client is None:
        return recent_signals_local(settings, limit)
    try:
        response = (
            client.table("trade_signals")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception:
        logger.exception("Supabase signal history fetch failed")
        return recent_signals_local(settings, limit)


def save_signal_local(settings: Settings, signal: SignalResponse) -> bool:
    try:
        path = Path(settings.local_journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = signal.model_dump(mode="json")
        record = {
            "id": f"local-{payload['created_at']}",
            "created_at": payload["created_at"],
            "symbol": signal.symbol,
            "mode": signal.mode,
            "signal": signal.signal,
            "confidence": signal.confidence,
            "risk_score": signal.risk_score,
            "price": signal.price,
            "btc_price": signal.btc_price,
            "entry": signal.suggestion.entry,
            "take_profit": signal.suggestion.take_profit,
            "stop_loss": signal.suggestion.stop_loss,
            "position_size": signal.suggestion.position_size,
            "daily_pnl_pct": signal.daily_pnl_pct,
            "indicators": signal.indicators.model_dump(mode="json"),
            "detections": signal.detections.model_dump(mode="json"),
            "reasoning_th": signal.reasoning_th,
            "reasoning_en": signal.reasoning_en,
            "personality_log": signal.personality_log,
            "raw_payload": payload,
            "journal_backend": "local",
        }
        with path.open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        logger.exception("Local signal journal write failed")
        return False


def recent_signals_local(settings: Settings, limit: int = 25) -> list[dict]:
    try:
        path = Path(settings.local_journal_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        records: list[dict] = []
        for line in reversed(lines[-limit:]):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
    except Exception:
        logger.exception("Local signal history fetch failed")
        return []
