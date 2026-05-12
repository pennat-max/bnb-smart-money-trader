from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .ai_committee import configured_ai_providers, generate_ai_committee_report
from .backtest import run_backtest
from .binance_client import BinanceFuturesClient
from .candles import backfill_candles, candle_status_supabase, collect_all_recent_candles, initial_candle_backfill
from .collector import market_record_from_signal, save_market_data
from .config import get_settings
from .journal import recent_signals, save_signal
from .learning import summarize_learning
from .line_alert import send_line_alert
from .market_data_repository import market_data_health
from .models import (
    AIReportRequest,
    BacktestRequest,
    CandleBackfillRequest,
    CandleBackfillResponse,
    CandleRecord,
    CandleStatusResponse,
    DerivativesMetrics,
    PaperRunRequest,
    PaperRunResponse,
    RuntimeStatus,
    TestnetOrderPreviewRequest,
)
from .paper import active_paper_trade, load_paper_trades, maybe_close_trade, open_paper_trade, paper_entry_block_reason
from .signal_engine import generate_signal

settings = get_settings()
app = FastAPI(title="BNB Smart Money AI Trader API", version="0.1.0")
logger = logging.getLogger(__name__)
paper_loop_task: asyncio.Task | None = None
market_collector_task: asyncio.Task | None = None
candle_collector_task: asyncio.Task | None = None

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


async def collect_market_cycle() -> str:
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    snapshot = await client.snapshot("BNBUSDT")
    signal_response = generate_signal(snapshot, settings)
    return save_market_data(settings, market_record_from_signal(signal_response))


async def market_collector_loop() -> None:
    while True:
        settings = get_settings()
        await asyncio.sleep(max(60, settings.market_collector_interval_seconds))
        if not settings.market_collector_enabled:
            continue
        try:
            await collect_market_cycle()
        except Exception:
            logger.exception("Market collector tick failed")


async def candle_collector_loop() -> None:
    did_initial_backfill = False
    while True:
        settings = get_settings()
        if not settings.candle_collector_enabled:
            await asyncio.sleep(max(60, settings.candle_collector_interval_seconds))
            continue

        try:
            client = BinanceFuturesClient(settings)
            if not did_initial_backfill:
                await initial_candle_backfill(settings, client)
                did_initial_backfill = True
            await collect_all_recent_candles(settings, client)
        except Exception:
            logger.exception("Candle collector tick failed")

        await asyncio.sleep(max(15, settings.candle_collector_interval_seconds))


@app.on_event("startup")
async def start_paper_loop() -> None:
    global paper_loop_task, market_collector_task, candle_collector_task
    if paper_loop_task is None:
        paper_loop_task = asyncio.create_task(paper_learning_loop())
    if market_collector_task is None:
        market_collector_task = asyncio.create_task(market_collector_loop())
    if candle_collector_task is None:
        candle_collector_task = asyncio.create_task(candle_collector_loop())


@app.on_event("shutdown")
async def stop_paper_loop() -> None:
    if paper_loop_task:
        paper_loop_task.cancel()
    if market_collector_task:
        market_collector_task.cancel()
    if candle_collector_task:
        candle_collector_task.cancel()


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
        market_collector_enabled=settings.market_collector_enabled,
        market_collector_interval_seconds=settings.market_collector_interval_seconds,
        candle_collector_enabled=settings.candle_collector_enabled,
        candle_collector_interval_seconds=settings.candle_collector_interval_seconds,
        candle_collector_symbols=settings.candle_symbols,
        candle_collector_timeframes=settings.candle_timeframes,
        ai_committee_enabled=settings.ai_committee_enabled,
        ai_providers_configured=configured_ai_providers(settings),
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


@app.get("/api/derivatives", response_model=DerivativesMetrics)
async def derivatives(symbol: str = Query(default="BNBUSDT"), period: str = Query(default="15m")):
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    context = await client.derivatives_context(symbol, period=period, limit=30)
    long_short_ratio = float(context["long_short_ratio"])
    taker_ratio = float(context["taker_buy_sell_ratio"])
    oi_change = float(context["open_interest_change_pct"])
    imbalance = float(context["bid_ask_imbalance"])
    note_parts = []
    if long_short_ratio > 1.6:
        note_parts.append("crowded longs")
    elif long_short_ratio < 0.7:
        note_parts.append("crowded shorts")
    if oi_change > 0.35:
        note_parts.append("OI expanding")
    if taker_ratio > 1.25:
        note_parts.append("taker buy pressure")
    elif taker_ratio < 0.8:
        note_parts.append("taker sell pressure")
    if imbalance > 0.12:
        note_parts.append("bid wall imbalance")
    elif imbalance < -0.12:
        note_parts.append("ask wall imbalance")
    if context["liquidation_spike"]:
        note_parts.append("liquidation spike")
    if float(context["liquidation_imbalance"]) > 0.35:
        note_parts.append("short liquidation pressure")
    elif float(context["liquidation_imbalance"]) < -0.35:
        note_parts.append("long liquidation pressure")

    return DerivativesMetrics(
        symbol=symbol,
        period=period,
        data_ok=bool(context["data_ok"]),
        open_interest_change_pct=oi_change,
        long_short_ratio=long_short_ratio,
        long_account=float(context["long_account"]),
        short_account=float(context["short_account"]),
        taker_buy_sell_ratio=taker_ratio,
        taker_buy_volume_ratio=float(context["taker_buy_volume_ratio"]),
        bid_ask_imbalance=imbalance,
        depth_bid_qty=float(context["depth_bid_qty"]),
        depth_ask_qty=float(context["depth_ask_qty"]),
        depth_wall_side=str(context["depth_wall_side"]),
        depth_wall_price=context["depth_wall_price"],
        liquidation_buy_qty=float(context["liquidation_buy_qty"]),
        liquidation_sell_qty=float(context["liquidation_sell_qty"]),
        liquidation_imbalance=float(context["liquidation_imbalance"]),
        liquidation_spike=bool(context["liquidation_spike"]),
        smart_money_note=", ".join(note_parts) if note_parts else "no strong derivatives imbalance",
    )


@app.post("/api/collect/market")
async def collect_market():
    return {"ok": True, "backend": await collect_market_cycle()}


@app.post("/api/candles/backfill", response_model=CandleBackfillResponse)
async def candles_backfill(request: CandleBackfillRequest):
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    try:
        fetched, saved = await backfill_candles(settings, client, request.symbol, request.timeframe, request.days)
        error = None
    except Exception as exc:
        logger.exception("Candle backfill failed")
        fetched = 0
        saved = 0
        error = str(exc)
    return CandleBackfillResponse(
        ok=saved > 0,
        symbol=request.symbol.upper(),
        timeframe=request.timeframe,
        days=request.days,
        fetched=fetched,
        saved=saved,
        backend="supabase" if saved > 0 else "none",
        error=error,
    )


@app.post("/api/candles/collect")
async def candles_collect():
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    results = await collect_all_recent_candles(settings, client)
    return {"ok": any(saved > 0 for saved in results.values()), "items": results}


@app.get("/api/candles/status", response_model=CandleStatusResponse)
async def candles_status(
    symbol: str = Query(default="BNBUSDT"),
    timeframe: str = Query(default="15m"),
):
    settings = get_settings()
    try:
        count, latest, error = candle_status_supabase(settings, symbol, timeframe)
        latest_candle = CandleRecord.model_validate(latest) if latest else None
    except Exception as exc:
        logger.exception("Candle status request failed")
        count = 0
        latest_candle = None
        error = str(exc)
    return CandleStatusResponse(
        ok=error is None,
        symbol=symbol.upper(),
        timeframe=timeframe,
        count=count,
        latest_candle=latest_candle,
        backend="supabase" if error is None else "none",
        error=error,
    )


@app.get("/api/market-data/health")
async def market_data_health_check():
    settings = get_settings()
    return market_data_health(settings)


@app.post("/api/backtest")
async def backtest(request: BacktestRequest):
    settings = get_settings()
    client = BinanceFuturesClient(settings)
    candles = await client.raw_klines_for_days(request.symbol, interval=request.interval, days=request.period_days)
    derivatives = await client.derivatives_history(request.symbol, period=request.interval, limit=500)
    return run_backtest(candles, settings, request, derivatives_history=derivatives)


@app.get("/api/learning")
async def learning():
    settings = get_settings()
    return summarize_learning([], load_paper_trades(settings, limit=500))


@app.post("/api/ai/report")
async def ai_report(request: AIReportRequest):
    settings = get_settings()
    return await generate_ai_committee_report(settings, request)


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
