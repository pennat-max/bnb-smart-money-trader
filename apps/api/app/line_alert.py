from __future__ import annotations

import logging

import httpx

from .config import Settings
from .models import SignalResponse

logger = logging.getLogger(__name__)


def build_line_message(signal: SignalResponse) -> str:
    entry = signal.suggestion.entry if signal.suggestion.entry is not None else "-"
    take_profit = signal.suggestion.take_profit if signal.suggestion.take_profit is not None else "-"
    stop_loss = signal.suggestion.stop_loss if signal.suggestion.stop_loss is not None else "-"
    return "\n".join(
        [
            f"BNB Smart Money: {signal.signal}",
            f"ราคา BNBUSDT: {signal.price}",
            f"Confidence: {signal.confidence}% | Risk: {signal.risk_score}%",
            f"Entry: {entry} | TP: {take_profit} | SL: {stop_loss}",
            signal.reasoning_th,
            "Signal-only: ไม่มีการส่งออเดอร์จริง",
        ]
    )


async def send_line_alert(settings: Settings, signal: SignalResponse) -> bool:
    if not settings.line_alert_enabled or not settings.line_configured:
        return False

    payload = {
        "to": settings.line_user_id,
        "messages": [{"type": "text", "text": build_line_message(signal)}],
    }
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.line.me/v2/bot/message/push", json=payload, headers=headers)
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("LINE alert send failed")
        return False
