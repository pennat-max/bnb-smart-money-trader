from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .learning import summarize_learning
from .models import BacktestRequest, BacktestResult, BacktestTrade, MarketSnapshot
from .signal_engine import generate_signal


@dataclass(frozen=True)
class BacktestProfile:
    name: str
    min_confidence: int = 70
    require_smart_money: bool = False
    require_trap: bool = False
    require_trend_stack: bool = False
    take_profit_multiplier: float = 1.8
    stop_loss_multiplier: float = 1.0


BASE_PROFILE = BacktestProfile(name="base", min_confidence=70)


WIN_RATE_PROFILES = [
    BASE_PROFILE,
    BacktestProfile(name="high_conf_75", min_confidence=75, take_profit_multiplier=1.2),
    BacktestProfile(name="high_conf_80", min_confidence=80, take_profit_multiplier=1.0),
    BacktestProfile(name="high_conf_85", min_confidence=85, take_profit_multiplier=0.8),
    BacktestProfile(name="scalp_70", min_confidence=70, take_profit_multiplier=0.45, stop_loss_multiplier=1.25),
    BacktestProfile(name="scalp_75", min_confidence=75, take_profit_multiplier=0.4, stop_loss_multiplier=1.35),
    BacktestProfile(name="scalp_80", min_confidence=80, take_profit_multiplier=0.35, stop_loss_multiplier=1.5),
    BacktestProfile(name="micro_tp_75", min_confidence=75, take_profit_multiplier=0.25, stop_loss_multiplier=1.8),
    BacktestProfile(name="micro_tp_80", min_confidence=80, take_profit_multiplier=0.25, stop_loss_multiplier=2.0),
    BacktestProfile(name="smart_money_75", min_confidence=75, require_smart_money=True, take_profit_multiplier=1.0),
    BacktestProfile(name="smart_money_80", min_confidence=80, require_smart_money=True, take_profit_multiplier=0.8),
    BacktestProfile(name="smart_scalp_75", min_confidence=75, require_smart_money=True, take_profit_multiplier=0.4, stop_loss_multiplier=1.5),
    BacktestProfile(name="smart_scalp_80", min_confidence=80, require_smart_money=True, take_profit_multiplier=0.3, stop_loss_multiplier=1.8),
    BacktestProfile(name="trap_only_70", min_confidence=70, require_trap=True, take_profit_multiplier=0.9),
    BacktestProfile(name="trap_only_75", min_confidence=75, require_trap=True, take_profit_multiplier=0.8),
    BacktestProfile(name="trap_scalp_70", min_confidence=70, require_trap=True, take_profit_multiplier=0.35, stop_loss_multiplier=1.6),
    BacktestProfile(name="trap_scalp_75", min_confidence=75, require_trap=True, take_profit_multiplier=0.3, stop_loss_multiplier=1.8),
    BacktestProfile(name="trend_stack_75", min_confidence=75, require_trend_stack=True, take_profit_multiplier=1.0),
    BacktestProfile(name="trend_stack_80", min_confidence=80, require_trend_stack=True, take_profit_multiplier=0.8),
    BacktestProfile(name="trend_scalp_75", min_confidence=75, require_trend_stack=True, take_profit_multiplier=0.4, stop_loss_multiplier=1.5),
    BacktestProfile(name="trend_scalp_80", min_confidence=80, require_trend_stack=True, take_profit_multiplier=0.3, stop_loss_multiplier=1.8),
    BacktestProfile(
        name="strict_smart_trend",
        min_confidence=78,
        require_smart_money=True,
        require_trend_stack=True,
        take_profit_multiplier=0.75,
        stop_loss_multiplier=1.1,
    ),
    BacktestProfile(
        name="strict_micro_tp",
        min_confidence=78,
        require_smart_money=True,
        require_trend_stack=True,
        take_profit_multiplier=0.25,
        stop_loss_multiplier=2.0,
    ),
]


def run_backtest(candles: list[dict], settings: Settings, request: BacktestRequest) -> BacktestResult:
    if request.optimize_for_win_rate:
        results = [run_backtest_profile(candles, settings, request, profile) for profile in WIN_RATE_PROFILES]
        eligible = [result for result in results if result.trades >= request.min_trades]
        candidates = eligible or results
        best = sorted(
            candidates,
            key=lambda result: (
                result.win_rate,
                result.total_pnl_pct,
                -result.max_drawdown_pct,
                result.trades,
            ),
            reverse=True,
        )[0]
        best.tested_profiles = [
            {
                "profile": result.profile,
                "trades": result.trades,
                "win_rate": result.win_rate,
                "pnl": result.total_pnl_pct,
                "max_dd": result.max_drawdown_pct,
            }
            for result in sorted(results, key=lambda item: item.win_rate, reverse=True)[:6]
        ]
        best.optimizer_note = (
            f"Optimizer selected {best.profile} for highest win rate with min {request.min_trades} trades. "
            "Higher win rate can reduce profit per trade, so still compare PnL and drawdown."
        )
        return best

    return run_backtest_profile(candles, settings, request, BASE_PROFILE)


def run_backtest_profile(
    candles: list[dict],
    settings: Settings,
    request: BacktestRequest,
    profile: BacktestProfile,
) -> BacktestResult:
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
        if signal.signal not in {"LONG", "SHORT"} or signal.confidence < profile.min_confidence:
            continue
        if profile.require_smart_money and not any(signal.detections.model_dump().values()):
            continue
        if profile.require_trap and not (signal.detections.trapped_longs or signal.detections.trapped_shorts):
            continue
        if profile.require_trend_stack:
            long_stack = signal.signal == "LONG" and signal.indicators.ema5 > signal.indicators.ema10 > signal.indicators.ema30
            short_stack = signal.signal == "SHORT" and signal.indicators.ema5 < signal.indicators.ema10 < signal.indicators.ema30
            if not (long_stack or short_stack):
                continue
        if signal.suggestion.entry is None or signal.suggestion.take_profit is None or signal.suggestion.stop_loss is None:
            continue

        entry = signal.suggestion.entry
        tp_distance = abs(signal.suggestion.take_profit - entry) * profile.take_profit_multiplier
        sl_distance = abs(entry - signal.suggestion.stop_loss) * profile.stop_loss_multiplier
        take_profit = round(entry + tp_distance, 2) if signal.signal == "LONG" else round(entry - tp_distance, 2)
        stop_loss = round(entry - sl_distance, 2) if signal.signal == "LONG" else round(entry + sl_distance, 2)

        outcome = "TIMEOUT"
        exit_price = candles[index + request.lookahead_candles]["close"]
        closed_at = candles[index + request.lookahead_candles]["close_time"]
        future = candles[index + 1 : index + request.lookahead_candles + 1]

        for future_candle in future:
            if signal.signal == "LONG":
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

        pnl_pct = ((exit_price - entry) / entry) * 100
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
                entry=entry,
                take_profit=take_profit,
                stop_loss=stop_loss,
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
        period_days=request.period_days,
        candles_tested=len(candles),
        trades=len(trades),
        wins=wins,
        losses=losses,
        timeouts=timeouts,
        win_rate=round((wins / len(trades)) * 100, 2) if trades else 0,
        total_pnl_pct=round(((balance - request.starting_balance) / request.starting_balance) * 100, 3),
        ending_balance=round(balance, 2),
        max_drawdown_pct=round(max_drawdown_pct, 3),
        learning_note=str(learning["note"]),
        profile=profile.name,
        optimizer_note="",
        tested_profiles=[],
        recent_trades=trades[-12:],
    )
