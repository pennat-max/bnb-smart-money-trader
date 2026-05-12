from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .binance_client import BinanceFuturesClient
from .config import get_settings
from .journal import recent_signals, save_signal
from .signal_engine import generate_signal

settings = get_settings()
app = FastAPI(title="BNB Smart Money AI Trader API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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


@app.get("/api/signal")
async def signal(
    daily_pnl_pct: float = Query(default=0),
    active_bnb_positions: int = Query(default=0),
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
    response.journal_saved = save_signal(settings, response)
    return response


@app.get("/api/history")
async def history(limit: int = Query(default=25, ge=1, le=100)):
    settings = get_settings()
    return {"items": recent_signals(settings, limit)}


@app.post("/api/testnet/order")
async def testnet_order_preview():
    settings = get_settings()
    if not settings.binance_use_testnet:
        return {"ok": False, "message": "Order testing is blocked unless BINANCE_USE_TESTNET=true."}
    return {
        "ok": True,
        "message": "Preview only. No live order placement is implemented in signal-only mode.",
        "mode": settings.app_mode,
    }
