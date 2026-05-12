from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .backtest import run_backtest
from .binance_client import BinanceFuturesClient
from .config import get_settings
from .journal import recent_signals, save_signal
from .learning import summarize_learning
from .line_alert import send_line_alert
from .models import BacktestRequest, PaperRunRequest, PaperRunResponse, RuntimeStatus, TestnetOrderPreviewRequest
from .paper import active_paper_trade, load_paper_trades, maybe_close_trade, open_paper_trade, paper_entry_block_reason
from .signal_engine import generate_signal

settings = get_settings()
app = FastAPI(title="BNB Smart Money AI Trader API", version="0.1.0")
logger = logging.getLogger(__name__)
paper_loop_task: asyncio.Task | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_paper_cycle(request: PaperRunRequest) -> PaperRunResponse:
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    snapshot = await client.snapshot("BNBUSDT")
    signal_response = generate_signal(
        snapshot,
        settings,
        daily_pnl_pct=request.daily_pnl_pct,
        active_bnb_positions=request.active_bnb_positions,
    )

    existing = active_paper_trade(settings)
    closed = maybe_close_trade(settings, existing, signal_response.price) if existing else None
    active = active_paper_trade(settings)
    block_reason = paper_entry_block_reason(settings, signal_response, active is not None)
    message = "Paper engine checked current market. No real order was sent."

    if request.enabled and active is None and closed is None:
        active = open_paper_trade(settings, signal_response, request.balance, request.risk_pct)
        if active:
            message = "Opened a paper-only simulated BNB position."
            block_reason = "เปิด paper position แล้ว รอ TP/SL เพื่อปิดผล."
        elif signal_response.signal in {"LONG", "SHORT"}:
            message = "Signal found, but paper entry was blocked by risk rules."
    elif closed:
        message = f"Closed paper trade as {closed.outcome}."
        block_reason = f"ปิด paper trade แล้วด้วยผล {closed.outcome}."

    learning_summary = summarize_learning([], load_paper_trades(settings, limit=500))
    return PaperRunResponse(
        ok=True,
        message=message,
        signal=signal_response.signal,
        confidence=signal_response.confidence,
        price=signal_response.price,
        last_tick_at=datetime.now(timezone.utc),
        entry_block_reason=block_reason,
        active_trade=active,
        closed_trade=closed,
        learning_summary=learning_summary,
    )


async def paper_learning_loop() -> None:
    while True:
        settings = get_settings()
        await asyncio.sleep(max(15, settings.paper_trading_interval_seconds))
        if not settings.paper_trading_enabled:
            continue
        try:
            await run_paper_cycle(
                PaperRunRequest(
                    enabled=True,
                    balance=settings.paper_starting_balance,
                    risk_pct=settings.paper_risk_pct,
                )
            )
        except Exception:
            logger.exception("Paper learning loop tick failed")


@app.on_event("startup")
async def start_paper_loop() -> None:
    global paper_loop_task
    if paper_loop_task is None:
        paper_loop_task = asyncio.create_task(paper_learning_loop())


@app.on_event("shutdown")
async def stop_paper_loop() -> None:
    if paper_loop_task:
        paper_loop_task.cancel()


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
        paper_trading_enabled=settings.paper_trading_enabled,
        paper_trading_interval_seconds=settings.paper_trading_interval_seconds,
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


@app.post("/api/backtest")
async def backtest(request: BacktestRequest):
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    candles = await client.raw_klines(request.symbol, interval=request.interval, limit=request.limit)
    return run_backtest(candles, settings, request)


@app.get("/api/learning")
async def learning():
    settings = get_settings()
    return summarize_learning([], load_paper_trades(settings, limit=500))


@app.post("/api/paper/run", response_model=PaperRunResponse)
async def paper_run(request: PaperRunRequest):
    return await run_paper_cycle(request)


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
