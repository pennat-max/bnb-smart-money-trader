"use client";

import { Activity, AlertTriangle, BarChart3, Brain, CheckCircle2, Clock3, Database, FlaskConical, LineChart, Play, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type RuntimeStatus = {
  mode: string;
  binance_testnet: boolean;
  real_trading: boolean;
  supabase_configured: boolean;
  paper_trading_enabled: boolean;
  paper_trading_interval_seconds: number;
  market_collector_enabled: boolean;
  market_collector_interval_seconds: number;
  candle_collector_enabled?: boolean;
  candle_collector_interval_seconds?: number;
  candle_collector_symbols?: string[];
  candle_collector_timeframes?: string[];
  ai_committee_enabled: boolean;
  ai_providers_configured: string[];
};

type SignalResponse = {
  mode: string;
  signal: "LONG" | "SHORT" | "WAIT" | "CANCEL";
  price: number;
  btc_price: number;
  confidence: number;
  risk_score: number;
  reasoning_th: string;
  journal_backend: "local" | "supabase" | "none";
};

type MarketDataHealth = {
  ok: boolean;
  status: "pass" | "warn" | "fail";
  symbols: string[];
  timeframes: string[];
  candles: Array<{
    symbol: string;
    timeframe: string;
    status: "pass" | "warn" | "fail";
    count: number;
    latest_open_time: number | null;
    latest_close_time: number | null;
    latest_age_seconds: number | null;
    gap_count_recent: number;
    recent_sample_size: number;
    error: string | null;
  }>;
  collector_runs: Array<{
    created_at: string;
    collector: string;
    status: "success" | "partial" | "failed";
    symbol: string | null;
    timeframe: string | null;
    rows_fetched: number;
    rows_saved: number;
    duration_ms: number | null;
    error: string | null;
  }>;
};

type BacktestResult = {
  interval: string;
  period_days: number;
  candles_tested: number;
  trades: number;
  win_rate: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  profile: string;
};

const apiUrl = "";

const phases = [
  { title: "Market Data", status: "active", text: "Historical candles, backfill, collector health, and gap checks." },
  { title: "Replay Engine", status: "next", text: "Stored-candle replay without strategy changes." },
  { title: "Backtest v2", status: "next", text: "Backtests reading Supabase candles and saving runs." },
  { title: "Execution Model", status: "planned", text: "Shared fees, slippage, TP/SL, equity curve, drawdown." },
  { title: "AI Analysis", status: "planned", text: "Analyze closed trades and regimes, no auto-parameter changes." },
  { title: "Research Dashboard", status: "active", text: "This page becomes the operating cockpit." }
];

export default function ResearchLab() {
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [marketDataHealth, setMarketDataHealth] = useState<MarketDataHealth | null>(null);
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      const [statusResponse, healthResponse, signalResponse] = await Promise.all([
        fetch(`${apiUrl}/status`, { cache: "no-store" }),
        fetch(`${apiUrl}/market-data-health`, { cache: "no-store" }),
        fetch(`${apiUrl}/live`, { cache: "no-store" })
      ]);

      if (statusResponse.ok) setRuntimeStatus((await statusResponse.json()) as RuntimeStatus);
      if (healthResponse.ok) setMarketDataHealth((await healthResponse.json()) as MarketDataHealth);
      if (signalResponse.ok) setSignal((await signalResponse.json()) as SignalResponse);
      if (!statusResponse.ok || !healthResponse.ok || !signalResponse.ok) {
        setError("Some backend checks are not responding.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown dashboard fetch error");
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 20000);
    return () => window.clearInterval(id);
  }, []);

  const totals = useMemo(() => {
    const candles = marketDataHealth?.candles ?? [];
    return {
      totalCandles: candles.reduce((sum, item) => sum + item.count, 0),
      gaps: candles.reduce((sum, item) => sum + item.gap_count_recent, 0),
      failing: candles.filter((item) => item.status === "fail").length,
      warning: candles.filter((item) => item.status === "warn").length
    };
  }, [marketDataHealth]);

  async function collectNow() {
    setMessage("Collecting latest candles...");
    try {
      const response = await fetch(`${apiUrl}/market-data-health`, { cache: "no-store" });
      if (response.ok) setMarketDataHealth((await response.json()) as MarketDataHealth);
      setMessage("Market data health refreshed.");
    } catch {
      setMessage("Refresh failed.");
    }
  }

  async function runQuickBacktest() {
    setBacktestRunning(true);
    setMessage("Running legacy quick backtest for reference only...");
    try {
      const response = await fetch(`${apiUrl}/backtest`, {
        body: JSON.stringify({
          symbol: "BNBUSDT",
          interval: "15m",
          period_days: 1,
          limit: 500,
          min_trades: 1,
          optimize_for_win_rate: false,
          smart_money_priority: true
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      });
      if (!response.ok) throw new Error("Backtest request failed");
      const payload = (await response.json()) as BacktestResult;
      setBacktestResult(payload);
      setMessage("Legacy backtest complete. Backtest v2 will replace this later.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backtest failed.");
    } finally {
      setBacktestRunning(false);
    }
  }

  return (
    <main className="labShell">
      <header className="labHeader">
        <div>
          <p className="eyebrow">Research-first / Signal-only / No real trading</p>
          <h1>AI Trading Research Lab</h1>
          <p className="headerText">Market data foundation first. Replay, backtest v2, shared execution, and AI analysis come after the data is stable.</p>
        </div>
        <button className="iconButton" onClick={refresh} title="Refresh lab" aria-label="Refresh lab">
          <Activity size={20} />
        </button>
      </header>

      {error && (
        <section className="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      )}

      <section className="safetyGrid">
        <StatusCard icon={<ShieldCheck />} label="Mode" value={runtimeStatus?.mode ?? "loading"} tone="cyan" />
        <StatusCard icon={<ShieldCheck />} label="Real Trading" value={runtimeStatus?.real_trading ? "LIVE" : "FALSE"} tone={runtimeStatus?.real_trading ? "red" : "green"} />
        <StatusCard icon={<Database />} label="Data Health" value={marketDataHealth?.status.toUpperCase() ?? "LOADING"} tone={marketDataHealth?.status === "pass" ? "green" : marketDataHealth?.status === "fail" ? "red" : "amber"} />
        <StatusCard icon={<Clock3 />} label="Collector" value={runtimeStatus?.candle_collector_enabled ? `${runtimeStatus.candle_collector_interval_seconds ?? 60}s` : "off"} tone="cyan" />
      </section>

      <section className="primaryGrid">
        <div className="panel marketPanel">
          <div className="panelHeader">
            <span>Market Data Foundation</span>
            <strong className={`healthPill ${marketDataHealth?.status ?? "warn"}`}>{marketDataHealth?.status.toUpperCase() ?? "LOADING"}</strong>
          </div>
          <div className="foundationStats">
            <Field label="Stored Candles" value={totals.totalCandles.toLocaleString()} />
            <Field label="Recent Gaps" value={`${totals.gaps}`} />
            <Field label="Warnings" value={`${totals.warning}`} />
            <Field label="Failures" value={`${totals.failing}`} />
          </div>
          <div className="healthGrid">
            {(marketDataHealth?.candles ?? []).map((item) => (
              <div className={`healthTile ${item.status}`} key={`${item.symbol}-${item.timeframe}`}>
                <div className="healthTileTop">
                  <strong>{item.symbol}</strong>
                  <span>{item.timeframe}</span>
                </div>
                <div className="healthStats">
                  <span>{item.count.toLocaleString()} candles</span>
                  <span>{formatAge(item.latest_age_seconds)}</span>
                  <span>{item.gap_count_recent} recent gaps</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Current Signal Safety Monitor</span>
            <ShieldCheck size={18} />
          </div>
          <div className="signalReadout">
            <strong className={`signalBadge ${(signal?.signal ?? "WAIT").toLowerCase()}`}>{signal?.signal ?? "WAIT"}</strong>
            <div>
              <span>BNBUSDT</span>
              <strong>{signal ? usd(signal.price) : "--"}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong>{signal?.confidence ?? 0}%</strong>
            </div>
          </div>
          <p className="reasoning">{signal?.reasoning_th ?? "Loading signal monitor..."}</p>
          <p className="saveState">Journal: {signal?.journal_backend ?? "--"} / Trading: {runtimeStatus?.real_trading ? "live" : "signal-only"}</p>
        </div>
      </section>

      <section className="phaseGrid">
        {phases.map((phase) => (
          <div className={`phaseCard ${phase.status}`} key={phase.title}>
            <div className="phaseTop">
              <CheckCircle2 size={17} />
              <strong>{phase.title}</strong>
            </div>
            <p>{phase.text}</p>
            <span>{phase.status}</span>
          </div>
        ))}
      </section>

      <section className="researchGrid">
        <div className="panel">
          <div className="panelHeader">
            <span>Collector Runs</span>
            <Database size={18} />
          </div>
          <div className="runList">
            {(marketDataHealth?.collector_runs ?? []).slice(0, 8).map((run) => (
              <div className={`runItem ${run.status}`} key={`${run.created_at}-${run.symbol}-${run.timeframe}`}>
                <strong>{run.symbol ?? "--"} {run.timeframe ?? "--"}</strong>
                <span>{run.collector} / {run.rows_saved} saved / {run.duration_ms ?? 0}ms</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Research Controls</span>
            <FlaskConical size={18} />
          </div>
          <div className="buttonStack">
            <button className="wideButton" onClick={collectNow}>
              <Database size={16} />
              Refresh Data Health
            </button>
            <button className="wideButton secondary" onClick={runQuickBacktest} disabled={backtestRunning}>
              {backtestRunning ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
              Legacy 1d Backtest
            </button>
          </div>
          <p className="saveState">{message ?? "Controls are research-only. No orders are sent."}</p>
          {backtestResult && (
            <div className="foundationStats">
              <Field label="Candles" value={`${backtestResult.candles_tested}`} />
              <Field label="Trades" value={`${backtestResult.trades}`} />
              <Field label="Win Rate" value={`${backtestResult.win_rate}%`} />
              <Field label="PnL" value={`${backtestResult.total_pnl_pct}%`} />
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Next Build Queue</span>
            <Brain size={18} />
          </div>
          <div className="queueList">
            <QueueItem icon={<LineChart />} title="Replay Engine" text="Read stored candles and replay windows." />
            <QueueItem icon={<BarChart3 />} title="Backtest v2" text="Use Supabase candles and save run results." />
            <QueueItem icon={<FlaskConical />} title="Shared Execution" text="One model for fees, slippage, TP/SL, drawdown." />
            <QueueItem icon={<Brain />} title="AI Reports" text="Persist analysis, classify setups, no auto-change." />
          </div>
        </div>
      </section>
    </main>
  );
}

function StatusCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: "green" | "red" | "amber" | "cyan" }) {
  return (
    <div className={`statusCard ${tone}`}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
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

function QueueItem({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="queueItem">
      <div>{icon}</div>
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function usd(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatAge(seconds: number | null) {
  if (seconds === null) return "--";
  if (seconds < 60) return `${seconds}s old`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m old`;
  return `${Math.round(seconds / 3600)}h old`;
}
