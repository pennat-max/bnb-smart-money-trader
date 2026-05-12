"use client";

import { Activity, AlertTriangle, BarChart3, Brain, Clock3, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
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

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Dashboard() {
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyPnl, setDailyPnl] = useState(0);

  async function refresh() {
    try {
      setError(null);
      const response = await fetch(`${apiUrl}/api/signal?daily_pnl_pct=${dailyPnl}`);
      if (!response.ok) throw new Error("API signal request failed");
      const data = (await response.json()) as SignalResponse;
      setSignal(data);

      const historyResponse = await fetch(`${apiUrl}/api/history?limit=12`);
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        setHistory(historyData.items ?? []);
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
  }, [dailyPnl]);

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
          <span>{error}. Start the FastAPI backend at {apiUrl}.</span>
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
          <div className="safetyLine">No real orders. Testnet-only order testing is locked behind backend safeguards.</div>
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
          </div>
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
          <div className="ruleList">
            <Rule ok={Boolean(signal?.risk_rules.confidence_ok)} label="Confidence >= 70" />
            <Rule ok={!Boolean(signal?.risk_rules.daily_loss_exceeded)} label="Max daily loss 2%" />
            <Rule ok={!Boolean(signal?.risk_rules.daily_target_reached)} label="Daily target 1%" />
            <Rule ok={Boolean(signal?.risk_rules.position_slot_available)} label="Max 1 active BNB position" />
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
          <p className="saveState">Journal: {signal?.journal_saved ? "saved to Supabase" : "local response only"}</p>
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
