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
  { title: "ข้อมูลตลาด", status: "กำลังใช้", text: "เก็บ candles ย้อนหลัง, backfill, ตรวจ collector และหา gap ของข้อมูล" },
  { title: "Replay Engine", status: "ถัดไป", text: "จำลองตลาดจาก candles ที่เก็บไว้ โดยยังไม่แก้ strategy" },
  { title: "Backtest v2", status: "ถัดไป", text: "ทดสอบย้อนหลังจาก Supabase candles และบันทึกผลการรัน" },
  { title: "Execution Model", status: "วางแผน", text: "ใช้โมเดลเดียวกันสำหรับ fees, slippage, TP/SL, equity curve และ drawdown" },
  { title: "AI Analysis", status: "วางแผน", text: "ให้ AI วิเคราะห์ trade ที่ปิดแล้วและ regime แต่ยังไม่ให้แก้ strategy อัตโนมัติ" },
  { title: "Research Dashboard", status: "กำลังใช้", text: "หน้านี้คือ cockpit หลักสำหรับงานวิจัยระบบเทรด" }
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
        setError("บางส่วนของ backend ยังไม่ตอบสนอง");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลหน้า dashboard ไม่สำเร็จ");
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
    setMessage("กำลังรีเฟรชสุขภาพข้อมูลตลาด...");
    try {
      const response = await fetch(`${apiUrl}/market-data-health`, { cache: "no-store" });
      if (response.ok) setMarketDataHealth((await response.json()) as MarketDataHealth);
      setMessage("รีเฟรชสุขภาพข้อมูลตลาดแล้ว");
    } catch {
      setMessage("รีเฟรชไม่สำเร็จ");
    }
  }

  async function runQuickBacktest() {
    setBacktestRunning(true);
    setMessage("กำลังรัน legacy backtest แบบเร็วเพื่ออ้างอิงเท่านั้น...");
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
      if (!response.ok) throw new Error("สั่ง backtest ไม่สำเร็จ");
      const payload = (await response.json()) as BacktestResult;
      setBacktestResult(payload);
      setMessage("Legacy backtest เสร็จแล้ว ต่อไป Backtest v2 จะมาแทนส่วนนี้");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backtest ไม่สำเร็จ");
    } finally {
      setBacktestRunning(false);
    }
  }

  return (
    <main className="labShell">
      <header className="labHeader">
        <div>
          <p className="eyebrow">Research-first / Signal-only / ไม่เทรดเงินจริง</p>
          <h1>ห้องวิจัย AI Trading</h1>
          <p className="headerText">เริ่มจากฐานข้อมูลตลาดให้แน่นก่อน แล้วค่อยต่อ Replay, Backtest v2, execution model กลาง และ AI analysis หลังจากข้อมูลเสถียรแล้ว</p>
        </div>
        <button className="iconButton" onClick={refresh} title="รีเฟรช" aria-label="รีเฟรช">
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
        <StatusCard icon={<ShieldCheck />} label="โหมดระบบ" value={runtimeStatus?.mode ?? "กำลังโหลด"} tone="cyan" />
        <StatusCard icon={<ShieldCheck />} label="เทรดเงินจริง" value={runtimeStatus?.real_trading ? "เปิดอยู่" : "ปิดอยู่"} tone={runtimeStatus?.real_trading ? "red" : "green"} />
        <StatusCard icon={<Database />} label="สุขภาพข้อมูล" value={thaiHealth(marketDataHealth?.status)} tone={marketDataHealth?.status === "pass" ? "green" : marketDataHealth?.status === "fail" ? "red" : "amber"} />
        <StatusCard icon={<Clock3 />} label="Collector" value={runtimeStatus?.candle_collector_enabled ? `${runtimeStatus.candle_collector_interval_seconds ?? 60}s` : "off"} tone="cyan" />
      </section>

      <section className="primaryGrid">
        <div className="panel marketPanel">
          <div className="panelHeader">
            <span>ฐานข้อมูลตลาด</span>
            <strong className={`healthPill ${marketDataHealth?.status ?? "warn"}`}>{thaiHealth(marketDataHealth?.status)}</strong>
          </div>
          <div className="foundationStats">
            <Field label="Candles ที่เก็บแล้ว" value={totals.totalCandles.toLocaleString()} />
            <Field label="Gap ล่าสุด" value={`${totals.gaps}`} />
            <Field label="คำเตือน" value={`${totals.warning}`} />
            <Field label="ปัญหา" value={`${totals.failing}`} />
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
                  <span>{item.gap_count_recent} gaps ล่าสุด</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>ตัวตรวจความปลอดภัยของ Signal</span>
            <ShieldCheck size={18} />
          </div>
          <div className="signalReadout">
            <strong className={`signalBadge ${(signal?.signal ?? "WAIT").toLowerCase()}`}>{signal?.signal ?? "WAIT"}</strong>
            <div>
              <span>BNBUSDT</span>
              <strong>{signal ? usd(signal.price) : "--"}</strong>
            </div>
            <div>
              <span>ความมั่นใจ</span>
              <strong>{signal?.confidence ?? 0}%</strong>
            </div>
          </div>
          <p className="reasoning">{signal?.reasoning_th ?? "กำลังโหลด signal monitor..."}</p>
          <p className="saveState">Journal: {signal?.journal_backend ?? "--"} / การเทรด: {runtimeStatus?.real_trading ? "live" : "signal-only"}</p>
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
            <span>ประวัติ Collector</span>
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
            <span>เครื่องมือวิจัย</span>
            <FlaskConical size={18} />
          </div>
          <div className="buttonStack">
            <button className="wideButton" onClick={collectNow}>
              <Database size={16} />
              รีเฟรชสุขภาพข้อมูล
            </button>
            <button className="wideButton secondary" onClick={runQuickBacktest} disabled={backtestRunning}>
              {backtestRunning ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
              Legacy Backtest 1 วัน
            </button>
          </div>
          <p className="saveState">{message ?? "เครื่องมือนี้ใช้เพื่อวิจัยเท่านั้น ไม่มีการส่ง order จริง"}</p>
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
            <span>ลำดับงานถัดไป</span>
            <Brain size={18} />
          </div>
          <div className="queueList">
            <QueueItem icon={<LineChart />} title="Replay Engine" text="อ่าน candles ที่เก็บไว้แล้วจำลองตลาดย้อนหลัง" />
            <QueueItem icon={<BarChart3 />} title="Backtest v2" text="ใช้ Supabase candles และบันทึกผลการรัน" />
            <QueueItem icon={<FlaskConical />} title="Shared Execution" text="ใช้โมเดลเดียวสำหรับ fees, slippage, TP/SL และ drawdown" />
            <QueueItem icon={<Brain />} title="AI Reports" text="บันทึกบทวิเคราะห์และจัดกลุ่ม setup โดยยังไม่แก้ strategy อัตโนมัติ" />
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
  if (seconds < 60) return `${seconds} วินาที`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} นาที`;
  return `${Math.round(seconds / 3600)} ชั่วโมง`;
}

function thaiHealth(status?: "pass" | "warn" | "fail") {
  if (status === "pass") return "ปกติ";
  if (status === "warn") return "เตือน";
  if (status === "fail") return "มีปัญหา";
  return "กำลังโหลด";
}
