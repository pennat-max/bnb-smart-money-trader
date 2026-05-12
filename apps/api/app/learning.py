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
        note = "AI learning: \u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e22\u0e31\u0e07\u0e19\u0e49\u0e2d\u0e22 \u0e43\u0e2b\u0e49 paper run \u0e15\u0e48\u0e2d\u0e2d\u0e35\u0e01\u0e2a\u0e31\u0e01\u0e23\u0e30\u0e22\u0e30\u0e01\u0e48\u0e2d\u0e19\u0e40\u0e1e\u0e34\u0e48\u0e21\u0e19\u0e49\u0e33\u0e2b\u0e19\u0e31\u0e01\u0e04\u0e27\u0e32\u0e21\u0e21\u0e31\u0e48\u0e19\u0e43\u0e08."
    elif win_rate >= 55 and total_pnl > 0:
        note = "AI learning: setup \u0e0a\u0e38\u0e14\u0e19\u0e35\u0e49\u0e40\u0e23\u0e34\u0e48\u0e21\u0e21\u0e35 edge \u0e1a\u0e27\u0e01 \u0e41\u0e15\u0e48\u0e22\u0e31\u0e07\u0e15\u0e49\u0e2d\u0e07\u0e04\u0e38\u0e21 risk \u0e41\u0e25\u0e30\u0e44\u0e21\u0e48\u0e43\u0e0a\u0e49\u0e40\u0e07\u0e34\u0e19\u0e08\u0e23\u0e34\u0e07."
    elif win_rate < 45 or total_pnl < 0:
        note = "AI learning: setup \u0e22\u0e31\u0e07\u0e2d\u0e48\u0e2d\u0e19 \u0e04\u0e27\u0e23\u0e25\u0e14 confidence \u0e41\u0e25\u0e30\u0e23\u0e2d confirmation \u0e40\u0e1e\u0e34\u0e48\u0e21."
    else:
        note = "AI learning: \u0e1c\u0e25\u0e22\u0e31\u0e07\u0e01\u0e25\u0e32\u0e07 \u0e46 \u0e43\u0e2b\u0e49\u0e40\u0e01\u0e47\u0e1a\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e15\u0e48\u0e2d\u0e41\u0e25\u0e30\u0e14\u0e39 drawdown."

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
