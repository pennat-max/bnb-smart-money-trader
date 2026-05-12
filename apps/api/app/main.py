from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .binance_client import BinanceFuturesClient
from .config import get_settings
from .journal import recent_signals, save_signal
from .line_alert import send_line_alert
from .models import RuntimeStatus, TestnetOrderPreviewRequest
from .signal_engine import generate_signal

settings = get_settings()
app = FastAPI(title="BNB Smart Money AI Trader API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "mode": settings.app_mode,
        "binance_testnet": settings.binance_use_testnet,
        "real_trading": False,
    }


@app.get("/api/status", response_model=RuntimeStatus)
async def runtime_status():
    settings = get_settings()
    supabase_configured = bool(settings.supabase_url and settings.active_supabase_key)
    return RuntimeStatus(
        mode=settings.app_mode,
        binance_testnet=settings.binance_use_testnet,
        real_trading=False,
        supabase_configured=supabase_configured,
        journal_backend="supabase" if supabase_configured else "local",
        line_alert_enabled=settings.line_alert_enabled,
        line_configured=settings.line_configured,
        risk_daily_target_pct=settings.risk_daily_target_pct,
        risk_max_daily_loss_pct=settings.risk_max_daily_loss_pct,
        risk_min_confidence=settings.risk_min_confidence,
        risk_max_active_bnb_positions=settings.risk_max_active_bnb_positions,
    )


@app.get("/api/signal")
async def signal(
    daily_pnl_pct: float = Query(default=0),
    active_bnb_positions: int = Query(default=0),
    send_alert: bool = Query(default=False),
):
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    snapshot = await client.snapshot("BNBUSDT")
    response = generate_signal(
        snapshot,
        settings,
        daily_pnl_pct=daily_pnl_pct,
        active_bnb_positions=active_bnb_positions,
    )
    response.journal_backend = save_signal(settings, response)
    response.journal_saved = response.journal_backend != "none"
    if send_alert and response.signal in {"LONG", "SHORT", "CANCEL"}:
        response.alert_sent = await send_line_alert(settings, response)
    return response


@app.get("/api/history")
async def history(limit: int = Query(default=25, ge=1, le=100)):
    settings = get_settings()
    return {"items": recent_signals(settings, limit)}


@app.post("/api/testnet/order")
async def testnet_order_preview(order: TestnetOrderPreviewRequest):
    settings = get_settings()
    if not settings.binance_use_testnet:
        return {"ok": False, "message": "Order testing is blocked unless BINANCE_USE_TESTNET=true."}
    if order.side not in {"LONG", "SHORT"}:
        return {"ok": False, "message": "No testnet preview for WAIT/CANCEL signals."}
    if order.confidence < settings.risk_min_confidence:
        return {"ok": False, "message": f"Blocked by confidence rule: {order.confidence} < {settings.risk_min_confidence}."}
    if order.position_size <= 0 or order.entry is None or order.take_profit is None or order.stop_loss is None:
        return {"ok": False, "message": "Missing entry, TP, SL, or positive position size."}
    return {
        "ok": True,
        "message": "Preview only. No live order placement is implemented in signal-only mode.",
        "mode": settings.app_mode,
        "order": order.model_dump(mode="json"),
    }
