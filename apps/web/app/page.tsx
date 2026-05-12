"use client";

import { Activity, AlertTriangle, BarChart3, Bell, Brain, Clock3, FlaskConical, History, Play, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type SignalType = "LONG" | "SHORT" | "WAIT" | "CANCEL";

type SignalResponse = {
  created_at: string;
  mode: string;
  symbol: string;
  signal: SignalType;
  price: number;
  btc_price: number;
  funding_rate: number;
  open_interest: number;
  open_interest_change_pct: number;
  long_short_ratio: number;
  taker_buy_sell_ratio: number;
  taker_buy_volume_ratio: number;
  bid_ask_imbalance: number;
  depth_wall_side: string;
  depth_wall_price: number | null;
  vwap: number;
  session_high: number;
  session_low: number;
  session_position: number;
  volume_zscore: number;
  mtf_bias: string;
  mtf_alignment_score: number;
  mtf_trends: Record<string, string>;
  liquidation_imbalance: number;
  liquidation_spike: boolean;
  reasoning_th: string;
  reasoning_en: string;
  confidence: number;
  risk_score: number;
  daily_pnl_pct: number;
  journal_saved: boolean;
  suggestion: {
    entry: number | null;
    take_profit: number | null;
    stop_loss: number | null;
    position_size: number;
  };
  indicators: {
    ema5: number;
    ema10: number;
    ema30: number;
    rsi: number;
    macd: number;
    macd_signal: number;
    macd_histogram: number;
    bb_upper: number;
    bb_middle: number;
    bb_lower: number;
  };
  detections: Record<string, boolean>;
  risk_rules: Record<string, boolean | number | string>;
  active_position: Record<string, string | number | null>;
  personality_log: string;
  journal_backend: "local" | "supabase" | "none";
  alert_sent: boolean;
};

type HistoryItem = {
  id: string;
  created_at: string;
  signal: SignalType;
  confidence: number;
  risk_score: number;
  price: number;
  reasoning_th: string;
  personality_log: string;
};

type RuntimeStatus = {
  mode: string;
  binance_testnet: boolean;
  real_trading: boolean;
  supabase_configured: boolean;
  journal_backend: "local" | "supabase" | "none" | "unknown";
  line_alert_enabled: boolean;
  line_configured: boolean;
  paper_trading_enabled: boolean;
  paper_trading_interval_seconds: number;
  market_collector_enabled: boolean;
  market_collector_interval_seconds: number;
  risk_daily_target_pct: number;
  risk_max_daily_loss_pct: number;
  risk_min_confidence: number;
  risk_max_active_bnb_positions: number;
};

type DerivativesMetrics = {
  data_ok: boolean;
  source: string;
  open_interest_change_pct: number;
  long_short_ratio: number;
  long_account: number;
  short_account: number;
  taker_buy_sell_ratio: number;
  taker_buy_volume_ratio: number;
  bid_ask_imbalance: number;
  depth_bid_qty: number;
  depth_ask_qty: number;
  depth_wall_side: string;
  depth_wall_price: number | null;
  liquidation_buy_qty: number;
  liquidation_sell_qty: number;
  liquidation_imbalance: number;
  liquidation_spike: boolean;
  smart_money_note: string;
};

type BacktestResult = {
  interval: string;
  period_days: number;
  candles_tested: number;
  trades: number;
  wins: number;
  losses: number;
  timeouts: number;
  win_rate: number;
  total_pnl_pct: number;
  gross_pnl_pct: number;
  cost_pct: number;
  ending_balance: number;
  max_drawdown_pct: number;
  learning_note: string;
  profile: string;
  optimizer_note: string;
  tested_profiles: Array<{
    profile: string;
    trades: number;
    win_rate: number;
    pnl: number;
    max_dd: number;
    smart_money: string;
  }>;
  walk_forward: Array<{
    segment: number;
    trades: number;
    win_rate: number;
    pnl: number;
    cost: number;
  }>;
};

type LearningSummary = {
  samples: number;
  wins: number;
  losses: number;
  timeouts: number;
  win_rate: number;
  total_pnl_pct: number;
  note: string;
};

type PaperRunResponse = {
  ok: boolean;
  message: string;
  signal: SignalType;
  confidence: number;
  price: number;
  last_tick_at: string;
  entry_block_reason: string;
  active_trade: {
    side: "LONG" | "SHORT";
    entry: number;
    take_profit: number;
    stop_loss: number;
    current_price: number;
    pnl_pct: number;
    outcome: string;
  } | null;
  closed_trade: {
    side: "LONG" | "SHORT";
    pnl_pct: number;
    outcome: string;
  } | null;
  learning_summary: LearningSummary;
};

const apiUrl = "";

export default function Dashboard() {
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyPnl, setDailyPnl] = useState(0);
  const [activePositions, setActivePositions] = useState(0);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [derivatives, setDerivatives] = useState<DerivativesMetrics | null>(null);
  const [orderPreview, setOrderPreview] = useState<string>("No testnet preview yet.");
  const [alertPreview, setAlertPreview] = useState<string>("LINE alert is optional and off until env vars are configured.");
  const [backtestLimit, setBacktestLimit] = useState(500);
  const [backtestDays, setBacktestDays] = useState(7);
  const [backtestInterval, setBacktestInterval] = useState<"1m" | "5m" | "15m" | "1h">("15m");
  const [optimizeWinRate, setOptimizeWinRate] = useState(true);
  const [smartMoneyPriority, setSmartMoneyPriority] = useState(true);
  const [minBacktestTrades, setMinBacktestTrades] = useState(10);
  const [feeBps, setFeeBps] = useState(4);
  const [slippageBps, setSlippageBps] = useState(2);
  const [walkForwardSplits, setWalkForwardSplits] = useState(4);
  const [paperEnabled, setPaperEnabled] = useState(false);
  const [paperBalance, setPaperBalance] = useState(1000);
  const [paperRisk, setPaperRisk] = useState(1);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestStartedAt, setBacktestStartedAt] = useState<string | null>(null);
  const [backtestStatus, setBacktestStatus] = useState("Backtest is idle.");
  const [learningSummary, setLearningSummary] = useState<LearningSummary | null>(null);
  const [paperStatus, setPaperStatus] = useState("Paper trading is off.");
  const [paperMonitor, setPaperMonitor] = useState<PaperRunResponse | null>(null);

  async function refresh() {
    try {
      setError(null);
      const response = await fetch(`${apiUrl}/live?daily_pnl_pct=${dailyPnl}&active_bnb_positions=${activePositions}`);
      if (!response.ok) throw new Error("API signal request failed");
      const data = (await response.json()) as SignalResponse;
      setSignal(data);

      const statusResponse = await fetch(`${apiUrl}/status`);
      if (statusResponse.ok) {
        setRuntimeStatus((await statusResponse.json()) as RuntimeStatus);
      }

      const historyResponse = await fetch(`${apiUrl}/journal?limit=12`);
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        setHistory(historyData.items ?? []);
      }

      const learningResponse = await fetch(`${apiUrl}/learning`);
      if (learningResponse.ok) {
        setLearningSummary((await learningResponse.json()) as LearningSummary);
      }

      const derivativesResponse = await fetch(`${apiUrl}/derivatives?symbol=BNBUSDT&period=15m`);
      if (derivativesResponse.ok) {
        setDerivatives((await derivativesResponse.json()) as DerivativesMetrics);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 15000);
    return () => window.clearInterval(id);
  }, [dailyPnl, activePositions]);

  async function previewTestnetOrder() {
    if (!signal) return;
    const response = await fetch(`${apiUrl}/testnet-order`, {
      body: JSON.stringify({
        symbol: signal.symbol,
        side: signal.signal,
        entry: signal.suggestion.entry,
        take_profit: signal.suggestion.take_profit,
        stop_loss: signal.suggestion.stop_loss,
        position_size: signal.suggestion.position_size,
        confidence: signal.confidence
      }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
    const payload = await response.json();
    setOrderPreview(payload.message ?? "Preview checked.");
  }

  async function sendLinePreview() {
    const response = await fetch(`${apiUrl}/live?daily_pnl_pct=${dailyPnl}&active_bnb_positions=${activePositions}&send_alert=true`);
    if (!response.ok) {
      setAlertPreview("LINE alert request failed.");
      return;
    }
    const payload = (await response.json()) as SignalResponse;
    setAlertPreview(payload.alert_sent ? "LINE alert sent." : "LINE alert not sent. Check LINE env vars or signal state.");
  }

  async function runBacktest() {
    setBacktestRunning(true);
    setBacktestStartedAt(new Date().toISOString());
    setBacktestStatus(`Running backtest for ${backtestDays} days on ${backtestInterval} candles...`);
    try {
      const response = await fetch(`${apiUrl}/backtest`, {
        body: JSON.stringify({
          symbol: "BNBUSDT",
          interval: backtestInterval,
          period_days: backtestDays,
          limit: backtestLimit,
          lookahead_candles: 30,
          starting_balance: paperBalance,
          optimize_for_win_rate: optimizeWinRate,
          smart_money_priority: smartMoneyPriority,
          min_trades: minBacktestTrades,
          fee_bps: feeBps,
          slippage_bps: slippageBps,
          walk_forward_splits: walkForwardSplits
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      });
      if (!response.ok) {
        setBacktestStatus("Backtest failed. Backend is not ready.");
        return;
      }
      const payload = (await response.json()) as BacktestResult;
      setBacktestResult(payload);
      setBacktestStatus(`Done: ${payload.candles_tested} candles, ${payload.trades} trades, ${payload.win_rate}% win rate.`);
    } catch {
      setBacktestStatus("Backtest failed. Network or backend error.");
    } finally {
      setBacktestRunning(false);
    }
  }

  async function runPaperOnce() {
    const response = await fetch(`${apiUrl}/paper-run`, {
      body: JSON.stringify({
        enabled: paperEnabled,
        balance: paperBalance,
        risk_pct: paperRisk,
        daily_pnl_pct: dailyPnl,
        active_bnb_positions: activePositions
      }),
      headers: { "content-type": "application/json" },
      method: "POST"
    });
    if (!response.ok) {
      setPaperStatus("Paper run failed. Backend is not ready.");
      return;
    }
    const payload = (await response.json()) as PaperRunResponse;
    setPaperStatus(payload.message);
    setPaperMonitor(payload);
    setLearningSummary(payload.learning_summary);
  }

  const detectedSetups = useMemo(() => {
    if (!signal) return [];
    return Object.entries(signal.detections)
      .filter(([, value]) => value)
      .map(([key]) => key.replaceAll("_", " "));
  }, [signal]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Signal-only / Binance Futures Testnet</p>
          <h1>BNB Smart Money AI Trader</h1>
        </div>
        <button className="iconButton" onClick={refresh} title="Refresh signal" aria-label="Refresh signal">
          <Activity size={20} />
        </button>
      </header>

      {error && (
        <section className="alert">
          <AlertTriangle size={18} />
          <span>{error}. Backend proxy is not responding yet.</span>
        </section>
      )}

      <section className="metricsGrid">
        <Metric label="BNBUSDT" value={signal ? usd(signal.price) : "--"} icon={<BarChart3 />} />
        <Metric label="BTCUSDT" value={signal ? usd(signal.btc_price) : "--"} icon={<Activity />} />
        <Metric label="Funding" value={signal ? pct(signal.funding_rate * 100) : "--"} icon={<Clock3 />} />
        <Metric label="Open Interest" value={signal ? compact(signal.open_interest) : "--"} icon={<Brain />} />
      </section>

      <section className="workspace">
        <div className="signalPanel">
          <div className="panelHeader">
            <span>Current Signal</span>
            <strong className={`signalBadge ${signal?.signal.toLowerCase() ?? "wait"}`}>
              {loading ? "LOADING" : signal?.signal ?? "WAIT"}
            </strong>
          </div>
          <div className="confidenceRow">
            <Gauge label="Confidence" value={signal?.confidence ?? 0} tone="green" />
            <Gauge label="Risk" value={signal?.risk_score ?? 0} tone="red" />
          </div>
          <p className="reasoning">{signal?.reasoning_th ?? "Waiting for market data..."}</p>
          <p className="reasoning muted">{signal?.reasoning_en ?? ""}</p>
        </div>

        <div className="orderPanel">
          <div className="panelHeader">
            <span>Active / Pending Order</span>
            <ShieldCheck size={18} />
          </div>
          <div className="orderGrid">
            <Field label="Entry" value={priceOrDash(signal?.suggestion.entry)} />
            <Field label="TP" value={priceOrDash(signal?.suggestion.take_profit)} />
            <Field label="SL" value={priceOrDash(signal?.suggestion.stop_loss)} />
            <Field label="Size" value={`${signal?.suggestion.position_size ?? 0} BNB`} />
          </div>
          <div className="actionRow">
            <button className="actionButton" onClick={previewTestnetOrder}>
              <FlaskConical size={16} />
              Testnet Preview
            </button>
            <button className="actionButton" onClick={sendLinePreview}>
              <Bell size={16} />
              LINE Test
            </button>
          </div>
          <div className="safetyLine">No real orders. Testnet-only order testing is locked behind backend safeguards.</div>
          <div className="safetyLine">{orderPreview}</div>
          <div className="safetyLine">{alertPreview}</div>
        </div>
      </section>

      <section className="detailsGrid">
        <div className="panel">
          <div className="panelHeader">
            <span>Indicators</span>
            {signal?.signal === "SHORT" ? <TrendingDown size={18} /> : <TrendingUp size={18} />}
          </div>
          <div className="denseGrid">
            <Field label="EMA 5" value={num(signal?.indicators.ema5)} />
            <Field label="EMA 10" value={num(signal?.indicators.ema10)} />
            <Field label="EMA 30" value={num(signal?.indicators.ema30)} />
            <Field label="RSI" value={num(signal?.indicators.rsi)} />
            <Field label="MACD" value={num(signal?.indicators.macd)} />
            <Field label="BB Mid" value={num(signal?.indicators.bb_middle)} />
            <Field label="OI Change" value={derivatives ? `${derivatives.open_interest_change_pct.toFixed(3)}%` : signal ? `${signal.open_interest_change_pct.toFixed(3)}%` : "--"} />
            <Field label="Long/Short" value={derivatives ? derivatives.long_short_ratio.toFixed(3) : num(signal?.long_short_ratio)} />
            <Field label="Taker Buy" value={derivatives ? `${(derivatives.taker_buy_volume_ratio * 100).toFixed(1)}%` : signal ? `${(signal.taker_buy_volume_ratio * 100).toFixed(1)}%` : "--"} />
            <Field label="Taker Ratio" value={derivatives ? derivatives.taker_buy_sell_ratio.toFixed(3) : num(signal?.taker_buy_sell_ratio)} />
            <Field label="Book Imbalance" value={derivatives ? derivatives.bid_ask_imbalance.toFixed(3) : "--"} />
            <Field label="Depth Wall" value={derivatives ? wallLabel(derivatives.depth_wall_side, derivatives.depth_wall_price) : wallLabel(signal?.depth_wall_side, signal?.depth_wall_price)} />
            <Field label="Liquidation" value={derivatives ? derivatives.liquidation_imbalance.toFixed(3) : num(signal?.liquidation_imbalance)} />
            <Field label="VWAP" value={signal?.vwap ? usd(signal.vwap) : "--"} />
            <Field label="Session" value={signal ? `${(signal.session_position * 100).toFixed(0)}%` : "--"} />
            <Field label="MTF Bias" value={signal ? `${signal.mtf_bias} / ${signal.mtf_alignment_score}` : "--"} />
            <Field label="Volume Z" value={num(signal?.volume_zscore)} />
            <Field label="Derivatives API" value={derivatives?.data_ok ? "online" : "--"} />
          </div>
          <p className="saveState">{derivatives?.smart_money_note ?? "Binance derivatives data loading..."}</p>
          <p className="saveState">
            MTF: {signal ? Object.entries(signal.mtf_trends).map(([tf, trend]) => `${tf} ${trend}`).join(" / ") : "loading..."}
          </p>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Risk Rules</span>
            <ShieldCheck size={18} />
          </div>
          <label className="pnlControl">
            Daily PnL %
            <input type="number" step="0.1" value={dailyPnl} onChange={(event) => setDailyPnl(Number(event.target.value))} />
          </label>
          <label className="pnlControl">
            Active BNB Positions
            <input
              min="0"
              type="number"
              value={activePositions}
              onChange={(event) => setActivePositions(Number(event.target.value))}
            />
          </label>
          <div className="ruleList">
            <Rule ok={Boolean(signal?.risk_rules.confidence_ok)} label={`Confidence >= ${runtimeStatus?.risk_min_confidence ?? 70}`} />
            <Rule ok={!Boolean(signal?.risk_rules.daily_loss_exceeded)} label={`Max daily loss ${runtimeStatus?.risk_max_daily_loss_pct ?? 2}%`} />
            <Rule ok={!Boolean(signal?.risk_rules.daily_target_reached)} label={`Daily target ${runtimeStatus?.risk_daily_target_pct ?? 1}%`} />
            <Rule ok={Boolean(signal?.risk_rules.position_slot_available)} label={`Max ${runtimeStatus?.risk_max_active_bnb_positions ?? 1} active BNB position`} />
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Setup History</span>
            <Clock3 size={18} />
          </div>
          <div className="setupTags">
            {(detectedSetups.length ? detectedSetups : ["no confirmed trap"]).map((setup) => (
              <span key={setup}>{setup}</span>
            ))}
          </div>
          <div className="historyList">
            {history.length === 0 ? (
              <p className="empty">Supabase history appears here after configuration.</p>
            ) : (
              history.map((item) => (
                <div className="historyItem" key={item.id}>
                  <strong>{item.signal}</strong>
                  <span>{usd(item.price)} / {item.confidence}%</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>BNB Personality Log</span>
            <Brain size={18} />
          </div>
          <p className="personality">{signal?.personality_log ?? "BNB bot is booting..."}</p>
          <p className="saveState">Journal: {journalLabel(signal)}</p>
          <p className="saveState">Supabase: {runtimeStatus?.supabase_configured ? "configured" : "not configured"}</p>
          <p className="saveState">LINE: {runtimeStatus?.line_configured ? "configured" : "not configured"}</p>
          <p className="saveState">
            Paper loop: {runtimeStatus?.paper_trading_enabled ? `on / ${runtimeStatus.paper_trading_interval_seconds}s` : "manual only"}
          </p>
          <p className="saveState">
            Market collector: {runtimeStatus?.market_collector_enabled ? `on / ${runtimeStatus.market_collector_interval_seconds}s` : "off"}
          </p>
          <p className="saveState">Trading: {runtimeStatus?.real_trading ? "live" : "signal-only"}</p>
        </div>
      </section>

      <section className="labGrid">
        <div className="panel">
          <div className="panelHeader">
            <span>Backtest Lab</span>
            <History size={18} />
          </div>
          <label className="pnlControl">
            Period
            <select value={backtestDays} onChange={(event) => setBacktestDays(Number(event.target.value))}>
              <option value={1}>1 day</option>
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
            </select>
          </label>
          <label className="pnlControl">
            Timeframe
            <select value={backtestInterval} onChange={(event) => setBacktestInterval(event.target.value as "1m" | "5m" | "15m" | "1h")}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
            </select>
          </label>
          <label className="pnlControl">
            Candle Limit (legacy)
            <input
              max="1500"
              min="150"
              step="50"
              type="number"
              value={backtestLimit}
              onChange={(event) => setBacktestLimit(Number(event.target.value))}
            />
          </label>
          <label className="toggleRow">
            <input type="checkbox" checked={optimizeWinRate} onChange={(event) => setOptimizeWinRate(event.target.checked)} />
            Optimize for highest win rate
          </label>
          <label className="toggleRow">
            <input type="checkbox" checked={smartMoneyPriority} onChange={(event) => setSmartMoneyPriority(event.target.checked)} />
            Smart money priority
          </label>
          <label className="pnlControl">
            Min Trades
            <input
              min="1"
              max="500"
              type="number"
              value={minBacktestTrades}
              onChange={(event) => setMinBacktestTrades(Number(event.target.value))}
            />
          </label>
          <div className="orderGrid">
            <label className="pnlControl">
              Fee bps
              <input
                min="0"
                max="50"
                step="0.5"
                type="number"
                value={feeBps}
                onChange={(event) => setFeeBps(Number(event.target.value))}
              />
            </label>
            <label className="pnlControl">
              Slippage bps
              <input
                min="0"
                max="100"
                step="0.5"
                type="number"
                value={slippageBps}
                onChange={(event) => setSlippageBps(Number(event.target.value))}
              />
            </label>
          </div>
          <label className="pnlControl">
            Walk-forward splits
            <input
              min="1"
              max="12"
              type="number"
              value={walkForwardSplits}
              onChange={(event) => setWalkForwardSplits(Number(event.target.value))}
            />
          </label>
          <button className="wideButton" onClick={runBacktest} disabled={backtestRunning}>
            {backtestRunning ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
            {backtestRunning ? "Running..." : "Run Backtest"}
          </button>
          <div className="monitorBox">
            <div>Status: {backtestStatus}</div>
            <div>Started: {backtestStartedAt ? new Date(backtestStartedAt).toLocaleString() : "not started"}</div>
            <div>Mode: historical simulation only, no real orders</div>
          </div>
          {backtestResult ? (
            <div className="resultGrid">
              <Field label="Trades" value={`${backtestResult.trades}`} />
              <Field label="Win Rate" value={`${backtestResult.win_rate}%`} />
              <Field label="PnL" value={`${backtestResult.total_pnl_pct}%`} />
              <Field label="Gross PnL" value={`${backtestResult.gross_pnl_pct}%`} />
              <Field label="Cost" value={`${backtestResult.cost_pct}%`} />
              <Field label="Max DD" value={`${backtestResult.max_drawdown_pct}%`} />
              <Field label="Candles" value={`${backtestResult.candles_tested}`} />
              <Field label="Range" value={`${backtestResult.period_days}d / ${backtestResult.interval}`} />
              <Field label="Profile" value={backtestResult.profile} />
              <Field label="Optimizer" value={smartMoneyPriority ? "smart money" : optimizeWinRate ? "win rate" : "off"} />
            </div>
          ) : (
            <p className="empty">Run historical test before trusting any setup.</p>
          )}
          {backtestResult && <p className="saveState">{backtestResult.learning_note}</p>}
          {backtestResult?.optimizer_note && <p className="saveState">{backtestResult.optimizer_note}</p>}
          {Boolean(backtestResult?.walk_forward?.length) && (
            <div className="profileList">
              {backtestResult?.walk_forward.map((segment) => (
                <div className="profileItem" key={segment.segment}>
                  <strong>Segment {segment.segment}</strong>
                  <span>
                    {segment.win_rate}% WR / {segment.trades} trades / {segment.pnl}% PnL / {segment.cost}% cost
                  </span>
                </div>
              ))}
            </div>
          )}
          {Boolean(backtestResult?.tested_profiles?.length) && (
            <div className="profileList">
              {backtestResult?.tested_profiles.map((profile) => (
                <div className="profileItem" key={profile.profile}>
                  <strong>{profile.profile}</strong>
                  <span>
                    {profile.smart_money === "yes" ? "SM / " : ""}
                    {profile.win_rate}% WR / {profile.trades} trades / {profile.pnl}% PnL
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Paper Trading</span>
            <FlaskConical size={18} />
          </div>
          <label className="toggleRow">
            <input type="checkbox" checked={paperEnabled} onChange={(event) => setPaperEnabled(event.target.checked)} />
            Paper mode enabled
          </label>
          <div className="orderGrid">
            <label className="pnlControl">
              Balance USDT
              <input type="number" value={paperBalance} onChange={(event) => setPaperBalance(Number(event.target.value))} />
            </label>
            <label className="pnlControl">
              Risk %
              <input max="5" min="0.1" step="0.1" type="number" value={paperRisk} onChange={(event) => setPaperRisk(Number(event.target.value))} />
            </label>
          </div>
          <button className="wideButton" onClick={runPaperOnce}>
            <Play size={16} />
            Run Paper Tick
          </button>
          <p className="saveState">{paperStatus}</p>
          <div className="monitorBox">
            <div>Loop: {runtimeStatus?.paper_trading_enabled ? `auto every ${runtimeStatus.paper_trading_interval_seconds}s` : "manual"}</div>
            <div>Last tick: {paperMonitor ? new Date(paperMonitor.last_tick_at).toLocaleString() : "waiting"}</div>
            <div>Last signal: {paperMonitor ? `${paperMonitor.signal} / ${paperMonitor.confidence}%` : "--"}</div>
            <div>{paperMonitor?.entry_block_reason ?? "Press Run Paper Tick to see why the bot is waiting."}</div>
          </div>
        </div>

        <div className="panel learningPanel">
          <div className="panelHeader">
            <span>AI Learning Memory</span>
            <Brain size={18} />
          </div>
          <div className="resultGrid">
            <Field label="Samples" value={`${learningSummary?.samples ?? 0}`} />
            <Field label="Win Rate" value={`${learningSummary?.win_rate ?? 0}%`} />
            <Field label="Wins / Losses" value={`${learningSummary?.wins ?? 0} / ${learningSummary?.losses ?? 0}`} />
            <Field label="Paper PnL" value={`${learningSummary?.total_pnl_pct ?? 0}%`} />
          </div>
          <p className="personality">{learningSummary?.note ?? "AI learning: waiting for paper and backtest samples."}</p>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="metric">
      <div className="metricIcon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Gauge({ label, value, tone }: { label: string; value: number; tone: "green" | "red" }) {
  return (
    <div className="gauge">
      <div className="gaugeTop">
        <span>{label}</span>
        <strong>{value}%</strong>
      </div>
      <div className="track">
        <div className={tone} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Rule({ ok, label }: { ok: boolean; label: string }) {
  return <div className={ok ? "rule ok" : "rule blocked"}>{label}</div>;
}

function usd(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function compact(value: number) {
  return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function pct(value: number) {
  return `${value.toFixed(4)}%`;
}

function num(value?: number) {
  return value === undefined ? "--" : value.toFixed(3);
}

function priceOrDash(value?: number | null) {
  return value ? usd(value) : "--";
}

function wallLabel(side?: string, price?: number | null) {
  if (!side || side === "neutral") return "neutral";
  return price ? `${side} ${usd(price)}` : side;
}

function journalLabel(signal: SignalResponse | null) {
  if (!signal?.journal_saved) return "local response only";
  if (signal.journal_backend === "supabase") return "saved to Supabase";
  if (signal.journal_backend === "local") return "saved to sandbox journal";
  return "saved to journal";
}
