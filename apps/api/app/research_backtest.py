from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from .backtest import run_backtest
from .collector import supabase_rest_headers
from .config import Settings
from .indicators import calculate_indicators
from .models import (
    BacktestRequest,
    BacktestResult,
    BacktestTrade,
    ResearchBacktestRunRequest,
    ResearchBacktestRunResponse,
    ResearchBacktestRunSummary,
)
from .research_mission import fetch_research_events, latest_research_mission, table_url

logger = logging.getLogger(__name__)


async def run_research_backtests(settings: Settings, request: ResearchBacktestRunRequest) -> ResearchBacktestRunResponse:
    mission = await latest_research_mission(settings)
    mission_id = request.mission_id or mission.job_id
    plan_items = (mission.recommended_plan.get("priority_order") or mission.recommended_plan.get("backtest_matrix") or [])[
        : request.max_items
    ]
    if not plan_items:
        return ResearchBacktestRunResponse(
            ok=False,
            mission_id=mission_id,
            auto_strategy_changes=settings.ai_auto_strategy_changes,
            runs=[],
            message_th="ยังไม่มี AI mission/backtest matrix ให้รัน กดเริ่ม AI วางแผนทดลองก่อน",
        )

    await update_job_status(settings, mission_id, "running")
    await insert_event(
        settings,
        mission_id,
        "backtest_v2_start",
        "running",
        "เริ่ม Backtest v2",
        f"กำลังรัน {len(plan_items)} ชุดจาก Supabase candles แบบ research-only ไม่มี order จริง",
        {"items": plan_items},
    )

    runs: list[ResearchBacktestRunSummary] = []
    for item in plan_items:
        symbol = str(item.get("symbol", "BNBUSDT")).upper()
        timeframe = str(item.get("timeframe", "15m"))
        days = int(item.get("days", 7))
        await insert_event(
            settings,
            mission_id,
            f"backtest_{symbol}_{timeframe}",
            "running",
            f"รัน {symbol} {timeframe}",
            f"ดึง candles ย้อนหลัง {days} วันจาก Supabase แล้วจำลอง TP/SL, fee, slippage",
            item,
        )
        summary = await run_one_backtest(settings, request, mission_id, symbol, timeframe, days)
        runs.append(summary)
        await insert_event(
            settings,
            mission_id,
            f"backtest_{symbol}_{timeframe}_done",
            "done" if summary.status == "done" else "warning",
            f"ผล {symbol} {timeframe}",
            summary.note_th,
            summary.model_dump(mode="json"),
        )

    best = choose_best_run(runs)
    status = "done" if any(run.status == "done" for run in runs) else "failed"
    await update_job_status(settings, mission_id, status)
    await insert_event(
        settings,
        mission_id,
        "backtest_v2_summary",
        "done" if best else "warning",
        "สรุป Backtest v2",
        best.note_th if best else "ยังไม่มีชุดที่รันสำเร็จพอสำหรับเลือกแผน paper simulation",
        {"best_run": best.model_dump(mode="json") if best else None},
    )
    return ResearchBacktestRunResponse(
        ok=bool(best),
        mission_id=mission_id,
        auto_strategy_changes=settings.ai_auto_strategy_changes,
        runs=runs,
        best_run=best,
        backend="supabase",
        message_th=(
            f"Backtest v2 เสร็จแล้ว เลือก {best.symbol} {best.timeframe} profile {best.profile} เป็นตัวเต็งสำหรับ paper simulation"
            if best
            else "Backtest v2 รันแล้ว แต่ยังไม่มีผลที่พอเลือกเป็นตัวเต็ง"
        ),
    )


async def run_one_backtest(
    settings: Settings,
    request: ResearchBacktestRunRequest,
    mission_id: str | None,
    symbol: str,
    timeframe: str,
    days: int,
) -> ResearchBacktestRunSummary:
    try:
        candles = fetch_candles_from_supabase(settings, symbol, timeframe, days)
        if len(candles) < 150:
            return ResearchBacktestRunSummary(
                symbol=symbol,
                timeframe=timeframe,
                period_days=days,
                status="skipped",
                candles_tested=len(candles),
                note_th=f"ข้าม {symbol} {timeframe}: candles น้อยเกินไป ({len(candles)})",
            )
        bt_request = BacktestRequest(
            symbol=symbol,
            interval=timeframe,  # type: ignore[arg-type]
            period_days=days,
            limit=min(len(candles), 1500),
            lookahead_candles=lookahead_for_timeframe(timeframe),
            starting_balance=request.starting_balance,
            optimize_for_win_rate=request.optimize_for_win_rate,
            smart_money_priority=request.smart_money_priority,
            min_trades=request.min_trades,
            fee_bps=4.0,
            slippage_bps=2.0,
            walk_forward_splits=4,
        )
        result = run_backtest(candles, settings, bt_request, derivatives_history=[])
        if result.trades < request.min_trades:
            result = run_exploratory_candle_backtest(candles, bt_request)
        run_id = save_backtest_result(settings, mission_id, result)
        save_backtest_trades(settings, mission_id, run_id, result.symbol, result.interval, result.all_trades)
        save_equity_curve(settings, mission_id, run_id, result.all_trades, request.starting_balance)
        return ResearchBacktestRunSummary(
            run_id=run_id,
            symbol=symbol,
            timeframe=timeframe,
            period_days=days,
            status="done",
            candles_tested=result.candles_tested,
            trades=result.trades,
            win_rate=result.win_rate,
            total_pnl_pct=result.total_pnl_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            profile=result.profile,
            note_th=backtest_note(result),
        )
    except Exception as exc:
        logger.exception("Research backtest failed")
        return ResearchBacktestRunSummary(
            symbol=symbol,
            timeframe=timeframe,
            period_days=days,
            status="failed",
            note_th=f"{symbol} {timeframe} รันไม่สำเร็จ: {str(exc)[:180]}",
            error=str(exc),
        )


def fetch_candles_from_supabase(settings: Settings, symbol: str, timeframe: str, days: int) -> list[dict]:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "candles")
    if headers is None or url is None:
        raise RuntimeError("Supabase is not configured.")

    start_time = int(datetime.now(timezone.utc).timestamp() * 1000) - days * 24 * 60 * 60 * 1000
    params = {
        "symbol": f"eq.{symbol.upper()}",
        "timeframe": f"eq.{timeframe}",
        "open_time": f"gte.{start_time}",
        "select": "open_time,close_time,open,high,low,close,volume",
        "order": "open_time.asc",
        "limit": "12000",
    }
    with httpx.Client(timeout=30) as client:
        response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        return []
    return [
        {
            "open_time": int(row["open_time"]),
            "close_time": int(row.get("close_time") or row["open_time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for row in rows
    ]


def save_backtest_result(settings: Settings, mission_id: str | None, result: BacktestResult) -> str | None:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "backtest_runs")
    if headers is None or url is None:
        return None
    payload = {
        "mission_id": mission_id,
        "strategy_version": "legacy_signal_engine_v1",
        "symbol": result.symbol,
        "timeframe": result.interval,
        "period_days": result.period_days,
        "status": "done",
        "candles_tested": result.candles_tested,
        "trades": result.trades,
        "wins": result.wins,
        "losses": result.losses,
        "timeouts": result.timeouts,
        "win_rate": result.win_rate,
        "total_pnl_pct": result.total_pnl_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "ending_balance": result.ending_balance,
        "profile": result.profile,
        "optimizer_note": result.optimizer_note,
        "learning_note": result.learning_note,
        "tested_profiles": result.tested_profiles,
        "walk_forward": result.walk_forward,
        "result_payload": result.model_dump(mode="json", exclude={"all_trades"}),
    }
    with httpx.Client(timeout=15) as client:
        response = client.post(url, json=payload, headers={**headers, "Prefer": "return=representation"})
        response.raise_for_status()
        rows = response.json()
    return rows[0]["id"] if rows else None


def save_backtest_trades(
    settings: Settings,
    mission_id: str | None,
    run_id: str | None,
    symbol: str,
    timeframe: str,
    trades: list[BacktestTrade],
) -> None:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "backtest_trades")
    if headers is None or url is None or run_id is None or not trades:
        return
    payload = [
        {
            "run_id": run_id,
            "mission_id": mission_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "side": trade.side,
            "entry": trade.entry,
            "take_profit": trade.take_profit,
            "stop_loss": trade.stop_loss,
            "exit_price": trade.exit_price,
            "outcome": trade.outcome,
            "pnl_pct": trade.pnl_pct,
            "gross_pnl_pct": trade.gross_pnl_pct,
            "cost_pct": trade.cost_pct,
            "confidence": trade.confidence,
            "reason": trade.reason,
            "raw_payload": trade.model_dump(mode="json"),
        }
        for trade in trades[:1000]
    ]
    with httpx.Client(timeout=20) as client:
        for index in range(0, len(payload), 200):
            response = client.post(url, json=payload[index : index + 200], headers={**headers, "Prefer": "return=minimal"})
            response.raise_for_status()


def save_equity_curve(
    settings: Settings,
    mission_id: str | None,
    run_id: str | None,
    trades: list[BacktestTrade],
    starting_balance: float,
) -> None:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "backtest_equity_curve")
    if headers is None or url is None or run_id is None:
        return
    equity = starting_balance
    peak = starting_balance
    points = [
        {
            "run_id": run_id,
            "mission_id": mission_id,
            "point_index": 0,
            "timestamp": trades[0].opened_at if trades else int(datetime.now(timezone.utc).timestamp() * 1000),
            "equity": round(equity, 4),
            "drawdown_pct": 0,
            "pnl_pct": 0,
        }
    ]
    for index, trade in enumerate(trades[:1000], start=1):
        equity *= 1 + trade.pnl_pct / 100
        peak = max(peak, equity)
        drawdown = ((peak - equity) / peak) * 100 if peak else 0
        points.append(
            {
                "run_id": run_id,
                "mission_id": mission_id,
                "point_index": index,
                "timestamp": trade.closed_at,
                "equity": round(equity, 4),
                "drawdown_pct": round(drawdown, 4),
                "pnl_pct": trade.pnl_pct,
            }
        )
    with httpx.Client(timeout=20) as client:
        for index in range(0, len(points), 200):
            response = client.post(url, json=points[index : index + 200], headers={**headers, "Prefer": "return=minimal"})
            response.raise_for_status()


async def insert_event(
    settings: Settings,
    mission_id: str | None,
    step: str,
    status: str,
    title_th: str,
    detail_th: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "research_events")
    if headers is None or url is None or mission_id is None:
        return
    payload = {
        "job_id": mission_id,
        "step": step,
        "status": status,
        "title_th": title_th,
        "detail_th": detail_th,
        "metadata": metadata or {},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload, headers={**headers, "Prefer": "return=minimal"})
        response.raise_for_status()


async def update_job_status(settings: Settings, mission_id: str | None, status: str) -> None:
    headers = supabase_rest_headers(settings)
    url = table_url(settings, "research_jobs")
    if headers is None or url is None or mission_id is None:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.patch(
            url,
            params={"id": f"eq.{mission_id}"},
            json={"status": status, "updated_at": datetime.now(timezone.utc).isoformat()},
            headers={**headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()


def lookahead_for_timeframe(timeframe: str) -> int:
    return {"1m": 45, "5m": 36, "15m": 30, "1h": 18}.get(timeframe, 30)


def choose_best_run(runs: list[ResearchBacktestRunSummary]) -> ResearchBacktestRunSummary | None:
    done = [run for run in runs if run.status == "done" and run.trades > 0]
    if not done:
        return None
    return sorted(
        done,
        key=lambda run: (
            run.total_pnl_pct > 0,
            run.win_rate,
            run.total_pnl_pct,
            -run.max_drawdown_pct,
            run.trades,
        ),
        reverse=True,
    )[0]


def backtest_note(result: BacktestResult) -> str:
    return (
        f"{result.symbol} {result.interval}: {result.trades} trades, win rate {result.win_rate}%, "
        f"PnL {result.total_pnl_pct}%, max DD {result.max_drawdown_pct}%, profile {result.profile}. "
        "ผลนี้เป็น backtest/paper research เท่านั้น ไม่ใช่คำแนะนำการลงทุน"
    )


def run_exploratory_candle_backtest(candles: list[dict], request: BacktestRequest) -> BacktestResult:
    trades: list[BacktestTrade] = []
    balance = request.starting_balance
    peak_balance = balance
    max_drawdown_pct = 0.0
    round_trip_cost_pct = (request.fee_bps * 2) / 100
    slippage_rate = request.slippage_bps / 10_000

    for index in range(120, len(candles) - request.lookahead_candles):
        window = candles[index - 120 : index]
        current = candles[index]
        ohlcv = [[row["open"], row["high"], row["low"], row["close"], row["volume"]] for row in window]
        indicators = calculate_indicators(ohlcv)
        price = current["close"]
        previous = candles[index - 1]
        recent_high = max(row["high"] for row in candles[index - 24 : index])
        recent_low = min(row["low"] for row in candles[index - 24 : index])
        bullish_stack = indicators.ema5 > indicators.ema10 > indicators.ema30 and indicators.macd_histogram > 0
        bearish_stack = indicators.ema5 < indicators.ema10 < indicators.ema30 and indicators.macd_histogram < 0
        bullish_sweep = current["low"] < recent_low and price > previous["close"]
        bearish_sweep = current["high"] > recent_high and price < previous["close"]

        side = None
        reason = ""
        confidence = 0
        if bullish_sweep and indicators.rsi < 70:
            side = "LONG"
            confidence = 74
            reason = "Research profile: bullish liquidity sweep + close reclaim, ใช้เฉพาะ backtest/paper"
        elif bearish_sweep and indicators.rsi > 30:
            side = "SHORT"
            confidence = 74
            reason = "Research profile: bearish liquidity sweep + rejection, ใช้เฉพาะ backtest/paper"
        elif bullish_stack and 42 <= indicators.rsi <= 68 and price > indicators.bb_middle:
            side = "LONG"
            confidence = 68
            reason = "Research profile: EMA/MACD trend stack + price above BB middle"
        elif bearish_stack and 32 <= indicators.rsi <= 58 and price < indicators.bb_middle:
            side = "SHORT"
            confidence = 68
            reason = "Research profile: EMA/MACD trend stack + price below BB middle"
        if side is None:
            continue

        raw_entry = price
        entry = raw_entry * (1 + slippage_rate) if side == "LONG" else raw_entry * (1 - slippage_rate)
        stop_distance = max(abs(price - indicators.bb_middle), price * 0.004)
        reward = 1.15 if confidence >= 72 else 0.85
        take_profit = round(raw_entry + stop_distance * reward, 2) if side == "LONG" else round(raw_entry - stop_distance * reward, 2)
        stop_loss = round(raw_entry - stop_distance, 2) if side == "LONG" else round(raw_entry + stop_distance, 2)
        outcome = "TIMEOUT"
        exit_price = candles[index + request.lookahead_candles]["close"]
        closed_at = candles[index + request.lookahead_candles]["close_time"]

        for future_candle in candles[index + 1 : index + request.lookahead_candles + 1]:
            if side == "LONG":
                if future_candle["low"] <= stop_loss:
                    outcome = "LOSS"
                    exit_price = stop_loss
                    closed_at = future_candle["close_time"]
                    break
                if future_candle["high"] >= take_profit:
                    outcome = "WIN"
                    exit_price = take_profit
                    closed_at = future_candle["close_time"]
                    break
            else:
                if future_candle["high"] >= stop_loss:
                    outcome = "LOSS"
                    exit_price = stop_loss
                    closed_at = future_candle["close_time"]
                    break
                if future_candle["low"] <= take_profit:
                    outcome = "WIN"
                    exit_price = take_profit
                    closed_at = future_candle["close_time"]
                    break

        slipped_exit = exit_price * (1 - slippage_rate) if side == "LONG" else exit_price * (1 + slippage_rate)
        gross_pnl_pct = ((slipped_exit - entry) / entry) * 100
        if side == "SHORT":
            gross_pnl_pct *= -1
        pnl_pct = round(gross_pnl_pct - round_trip_cost_pct, 3)
        gross_pnl_pct = round(gross_pnl_pct, 3)
        balance *= 1 + pnl_pct / 100
        peak_balance = max(peak_balance, balance)
        drawdown = ((peak_balance - balance) / peak_balance) * 100 if peak_balance else 0
        max_drawdown_pct = max(max_drawdown_pct, drawdown)
        trades.append(
            BacktestTrade(
                opened_at=current["open_time"],
                closed_at=closed_at,
                side=side,  # type: ignore[arg-type]
                entry=round(entry, 2),
                take_profit=take_profit,
                stop_loss=stop_loss,
                exit_price=round(exit_price, 2),
                outcome=outcome,  # type: ignore[arg-type]
                pnl_pct=pnl_pct,
                gross_pnl_pct=gross_pnl_pct,
                cost_pct=round(round_trip_cost_pct, 3),
                confidence=confidence,
                reason=reason,
            )
        )

    wins = sum(1 for trade in trades if trade.outcome == "WIN")
    losses = sum(1 for trade in trades if trade.outcome == "LOSS")
    timeouts = sum(1 for trade in trades if trade.outcome == "TIMEOUT")
    return BacktestResult(
        symbol=request.symbol,
        interval=request.interval,
        period_days=request.period_days,
        candles_tested=len(candles),
        trades=len(trades),
        wins=wins,
        losses=losses,
        timeouts=timeouts,
        win_rate=round((wins / len(trades)) * 100, 2) if trades else 0,
        gross_pnl_pct=round(sum(trade.gross_pnl_pct for trade in trades), 3),
        cost_pct=round(sum(trade.cost_pct for trade in trades), 3),
        total_pnl_pct=round(((balance - request.starting_balance) / request.starting_balance) * 100, 3),
        ending_balance=round(balance, 2),
        max_drawdown_pct=round(max_drawdown_pct, 3),
        walk_forward=[],
        learning_note="Exploratory candle-only research fallback. ใช้เพื่อหา candidate สำหรับ paper simulation เท่านั้น",
        profile="exploratory_smc_candle_v1",
        optimizer_note="Legacy signal produced too few trades on stored candles, so Backtest v2 used a research-only candle profile.",
        tested_profiles=[],
        recent_trades=trades[-12:],
        all_trades=trades,
    )
