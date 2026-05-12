from __future__ import annotations

from .config import Settings


def evaluate_risk_rules(
    settings: Settings,
    confidence: int,
    daily_pnl_pct: float,
    active_bnb_positions: int,
) -> dict[str, bool | float | int | str]:
    return {
        "daily_target_pct": settings.risk_daily_target_pct,
        "max_daily_loss_pct": settings.risk_max_daily_loss_pct,
        "min_confidence": settings.risk_min_confidence,
        "max_active_bnb_positions": settings.risk_max_active_bnb_positions,
        "daily_target_reached": daily_pnl_pct >= settings.risk_daily_target_pct,
        "daily_loss_exceeded": daily_pnl_pct <= -settings.risk_max_daily_loss_pct,
        "confidence_ok": confidence >= settings.risk_min_confidence,
        "position_slot_available": active_bnb_positions < settings.risk_max_active_bnb_positions,
        "mode": settings.app_mode,
    }


def should_cancel(rules: dict[str, bool | float | int | str]) -> bool:
    return bool(
        rules["daily_target_reached"]
        or rules["daily_loss_exceeded"]
        or not rules["confidence_ok"]
        or not rules["position_slot_available"]
    )
