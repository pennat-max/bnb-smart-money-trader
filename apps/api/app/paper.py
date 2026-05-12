from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from .config import Settings
from .models import PaperTradeRecord, SignalResponse

logger = logging.getLogger(__name__)


def paper_path(settings: Settings) -> Path:
    base = Path(settings.local_journal_path)
    return base.with_name("paper_trades.jsonl")


def load_paper_trades(settings: Settings, limit: int = 200) -> list[PaperTradeRecord]:
    supabase_records = load_paper_trades_supabase(settings, limit)
    if supabase_records:
        return supabase_records

    path = paper_path(settings)
    if not path.exists():
        return []

    records: list[PaperTradeRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            records.append(PaperTradeRecord.model_validate(json.loads(line)))
        except Exception:
            continue
    return records


def append_paper_trade(settings: Settings, trade: PaperTradeRecord) -> None:
    if append_paper_trade_supabase(settings, trade):
        return

    path = paper_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trade.model_dump(mode="json"), ensure_ascii=False) + "\n")


def active_paper_trade(settings: Settings) -> PaperTradeRecord | None:
    open_trades: dict[str, PaperTradeRecord] = {}
    for trade in load_paper_trades(settings, limit=500):
        if trade.status == "OPEN":
            open_trades[trade.id] = trade
        elif trade.id in open_trades:
            del open_trades[trade.id]
    return next(iter(open_trades.values()), None)


def maybe_close_trade(settings: Settings, trade: PaperTradeRecord, current_price: float) -> PaperTradeRecord | None:
    outcome = "OPEN"
    exit_price: float | None = None
    if trade.side == "LONG":
        if current_price >= trade.take_profit:
            outcome = "WIN"
            exit_price = trade.take_profit
        elif current_price <= trade.stop_loss:
            outcome = "LOSS"
            exit_price = trade.stop_loss
    else:
        if current_price <= trade.take_profit:
            outcome = "WIN"
            exit_price = trade.take_profit
        elif current_price >= trade.stop_loss:
            outcome = "LOSS"
            exit_price = trade.stop_loss

    if outcome == "OPEN" or exit_price is None:
        return None

    pnl_pct = ((exit_price - trade.entry) / trade.entry) * 100
    if trade.side == "SHORT":
        pnl_pct *= -1
    closed = trade.model_copy(
        update={
            "status": "CLOSED",
            "updated_at": datetime.now(timezone.utc),
            "current_price": current_price,
            "exit_price": exit_price,
            "pnl_pct": round(pnl_pct, 3),
            "pnl_usdt": round((pnl_pct / 100) * trade.size * trade.entry, 4),
            "outcome": outcome,
        }
    )
    append_paper_trade(settings, closed)
    return closed


def open_paper_trade(settings: Settings, signal: SignalResponse, balance: float, risk_pct: float) -> PaperTradeRecord | None:
    if signal.signal not in {"LONG", "SHORT"}:
        return None
    if signal.confidence < settings.risk_min_confidence:
        return None
    if not signal.suggestion.entry or not signal.suggestion.take_profit or not signal.suggestion.stop_loss:
        return None

    risk_usdt = balance * (risk_pct / 100)
    stop_distance = abs(signal.suggestion.entry - signal.suggestion.stop_loss)
    size = round(risk_usdt / stop_distance, 4) if stop_distance > 0 else signal.suggestion.position_size
    trade = PaperTradeRecord(
        id=f"paper-{uuid4()}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        symbol=signal.symbol,
        side=signal.signal,
        status="OPEN",
        entry=signal.suggestion.entry,
        take_profit=signal.suggestion.take_profit,
        stop_loss=signal.suggestion.stop_loss,
        size=max(0, size),
        confidence=signal.confidence,
        opened_price=signal.price,
        current_price=signal.price,
        reasoning_th=signal.reasoning_th,
    )
    append_paper_trade(settings, trade)
    return trade


def paper_entry_block_reason(settings: Settings, signal: SignalResponse, has_active_trade: bool) -> str:
    if has_active_trade:
        return "มี paper position เปิดอยู่แล้ว ระบบจำกัดไว้ทีละ 1 BNB position."
    if signal.signal not in {"LONG", "SHORT"}:
        return f"ยังไม่เข้า เพราะ signal เป็น {signal.signal}; ระบบเข้าเฉพาะ LONG/SHORT เท่านั้น."
    if signal.confidence < settings.risk_min_confidence:
        return f"ยังไม่เข้า เพราะ confidence {signal.confidence}% ต่ำกว่า {settings.risk_min_confidence}%."
    if not signal.suggestion.entry or not signal.suggestion.take_profit or not signal.suggestion.stop_loss:
        return "ยังไม่เข้า เพราะ entry/TP/SL ยังไม่ครบ."
    return "พร้อมเปิด paper position เมื่อ tick ถัดไป."


def supabase_rest_headers(settings: Settings) -> dict[str, str] | None:
    key = settings.active_supabase_key
    if not settings.supabase_url or not key:
        return None

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_publishable_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def paper_record(trade: PaperTradeRecord) -> dict:
    payload = trade.model_dump(mode="json")
    return {
        **payload,
        "raw_payload": payload,
    }


def append_paper_trade_supabase(settings: Settings, trade: PaperTradeRecord) -> bool:
    headers = supabase_rest_headers(settings)
    if headers is None or not settings.supabase_url:
        return False

    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/paper_trades"
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                url,
                params={"on_conflict": "id"},
                json=paper_record(trade),
                headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("Supabase REST paper trade insert failed")
        return False


def load_paper_trades_supabase(settings: Settings, limit: int = 200) -> list[PaperTradeRecord]:
    headers = supabase_rest_headers(settings)
    if headers is None or not settings.supabase_url:
        return []

    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/paper_trades"
    params = {
        "select": "*",
        "order": "updated_at.asc",
        "limit": str(limit),
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            return []
        return [PaperTradeRecord.model_validate(item) for item in data]
    except Exception:
        logger.exception("Supabase REST paper trade fetch failed")
        return []
