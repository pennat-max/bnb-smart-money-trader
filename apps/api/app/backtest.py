from __future__ import annotations

from .config import Settings
from .learning import summarize_learning
from .models import BacktestRequest, BacktestResult, BacktestTrade, MarketSnapshot
from .signal_engine import generate_signal


def run_backtest(candles: list[dict], settings: Settings, request: BacktestRequest) -> BacktestResult:
    trades: list[BacktestTrade] = []
    balance = request.starting_balance
    peak_balance = balance
    max_drawdown_pct = 0.0

    for index in range(120, len(candles) - request.lookahead_candles):
        window = candles[index - 120 : index]
        current = candles[index]
        snapshot = MarketSnapshot(
            symbol=request.symbol,
            price=current["close"],
            btc_price=0,
            funding_rate=0,
            open_interest=0,
            candles=[[row["open"], row["high"], row["low"], row["close"], row["volume"]] for row in window],
        )
        signal = generate_signal(snapshot, settings)
        if signal.signal not in {"LONG", "SHORT"} or signal.confidence < settings.risk_min_confidence:
            continue
        if signal.suggestion.entry is None or signal.suggestion.take_profit is None or signal.suggestion.stop_loss is None:
            continue

        outcome = "TIMEOUT"
        exit_price = candles[index + request.lookahead_candles]["close"]
        closed_at = candles[index + request.lookahead_candles]["close_time"]
        future = candles[index + 1 : index + request.lookahead_candles + 1]

        for future_candle in future:
            if signal.signal == "LONG":
                if future_candle["low"] <= signal.suggestion.stop_loss:
                    outcome = "LOSS"
                    exit_price = signal.suggestion.stop_loss
                    closed_at = future_candle["close_time"]
                    break
                if future_candle["high"] >= signal.suggestion.take_profit:
                    outcome = "WIN"
                    exit_price = signal.suggestion.take_profit
                    closed_at = future_candle["close_time"]
                    break
            else:
                if future_candle["high"] >= signal.suggestion.stop_loss:
                    outcome = "LOSS"
                    exit_price = signal.suggestion.stop_loss
                    closed_at = future_candle["close_time"]
                    break
                if future_candle["low"] <= signal.suggestion.take_profit:
                    outcome = "WIN"
                    exit_price = signal.suggestion.take_profit
                    closed_at = future_candle["close_time"]
                    break

        pnl_pct = ((exit_price - signal.suggestion.entry) / signal.suggestion.entry) * 100
        if signal.signal == "SHORT":
            pnl_pct *= -1
        pnl_pct = round(pnl_pct, 3)
        balance *= 1 + (pnl_pct / 100)
        peak_balance = max(peak_balance, balance)
        drawdown = ((peak_balance - balance) / peak_balance) * 100 if peak_balance else 0
        max_drawdown_pct = max(max_drawdown_pct, drawdown)
        trades.append(
            BacktestTrade(
                opened_at=current["open_time"],
                closed_at=closed_at,
                side=signal.signal,
                entry=signal.suggestion.entry,
                take_profit=signal.suggestion.take_profit,
                stop_loss=signal.suggestion.stop_loss,
                exit_price=round(exit_price, 2),
                outcome=outcome,
                pnl_pct=pnl_pct,
                confidence=signal.confidence,
                reason=signal.reasoning_th,
            )
        )

    wins = sum(1 for trade in trades if trade.outcome == "WIN")
    losses = sum(1 for trade in trades if trade.outcome == "LOSS")
    timeouts = sum(1 for trade in trades if trade.outcome == "TIMEOUT")
    learning = summarize_learning(trades)
    return BacktestResult(
        symbol=request.symbol,
        interval=request.interval,
        trades=len(trades),
        wins=wins,
        losses=losses,
        timeouts=timeouts,
        win_rate=round((wins / len(trades)) * 100, 2) if trades else 0,
        total_pnl_pct=round(((balance - request.starting_balance) / request.starting_balance) * 100, 3),
        ending_balance=round(balance, 2),
        max_drawdown_pct=round(max_drawdown_pct, 3),
        learning_note=str(learning["note"]),
        recent_trades=trades[-12:],
    )
