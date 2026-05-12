from __future__ import annotations

from collections import Counter

from .models import BacktestTrade, PaperTradeRecord


def summarize_learning(backtest_trades: list[BacktestTrade], paper_trades: list[PaperTradeRecord] | None = None) -> dict[str, float | int | str]:
    paper_trades = paper_trades or []
    outcomes = [trade.outcome for trade in backtest_trades] + [
        trade.outcome for trade in paper_trades if trade.outcome in {"WIN", "LOSS", "TIMEOUT"}
    ]
    counts = Counter(outcomes)
    completed = counts["WIN"] + counts["LOSS"] + counts["TIMEOUT"]
    win_rate = round((counts["WIN"] / completed) * 100, 2) if completed else 0
    total_pnl = round(
        sum(trade.pnl_pct for trade in backtest_trades)
        + sum(trade.pnl_pct for trade in paper_trades if trade.status == "CLOSED"),
        3,
    )

    if completed < 10:
        note = "AI learning: ข้อมูลยังน้อย ให้ paper run ต่ออีกสักระยะก่อนเพิ่มน้ำหนักความมั่นใจ."
    elif win_rate >= 55 and total_pnl > 0:
        note = "AI learning: setup ชุดนี้เริ่มมี edge บวก แต่ยังต้องคุม risk และไม่ใช้เงินจริง."
    elif win_rate < 45 or total_pnl < 0:
        note = "AI learning: setup ยังอ่อน ควรลด confidence และรอ confirmation เพิ่ม."
    else:
        note = "AI learning: ผลยังกลาง ๆ ให้เก็บข้อมูลต่อและดู drawdown."

    return {
        "samples": completed,
        "wins": counts["WIN"],
        "losses": counts["LOSS"],
        "timeouts": counts["TIMEOUT"],
        "win_rate": win_rate,
        "total_pnl_pct": total_pnl,
        "note": note,
    }


def confidence_adjustment(summary: dict[str, float | int | str]) -> int:
    samples = int(summary.get("samples", 0))
    win_rate = float(summary.get("win_rate", 0))
    total_pnl = float(summary.get("total_pnl_pct", 0))
    if samples < 20:
        return 0
    if win_rate >= 58 and total_pnl > 0:
        return 4
    if win_rate <= 42 or total_pnl < -2:
        return -6
    return 0
