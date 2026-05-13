"use client";

import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock3,
  Database,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type RuntimeStatus = {
  mode: string;
  real_trading: boolean;
  candle_collector_enabled?: boolean;
  candle_collector_interval_seconds?: number;
  ai_research_enabled?: boolean;
  ai_auto_strategy_changes?: boolean;
  ai_providers_configured: string[];
};

type MarketDataHealth = {
  ok: boolean;
  status: "pass" | "warn" | "fail";
  candles: Array<{
    symbol: string;
    timeframe: string;
    status: "pass" | "warn" | "fail";
    count: number;
    latest_age_seconds: number | null;
    gap_count_recent: number;
  }>;
  collector_runs: Array<{
    created_at: string;
    collector: string;
    status: "success" | "partial" | "failed";
    symbol: string | null;
    timeframe: string | null;
    rows_saved: number;
    duration_ms: number | null;
  }>;
};

type ResearchEvent = {
  id?: string | null;
  created_at: string;
  step: string;
  status: "queued" | "running" | "done" | "blocked" | "warning";
  title_th: string;
  detail_th: string;
  metadata: Record<string, unknown>;
};

type ResearchMission = {
  ok: boolean;
  job_id: string | null;
  status: "planned" | "running" | "done" | "blocked" | "failed";
  mode: string;
  real_trading: boolean;
  auto_strategy_changes: boolean;
  goal: string;
  recommended_plan: {
    backtest_matrix?: Array<{ symbol: string; timeframe: string; days: number; purpose: string; execution: string }>;
    selection_rules?: string[];
    paper_simulation?: { mode?: string; risk?: string; enabled_after_human_review?: boolean };
    safety?: { note_th?: string };
  };
  events: ResearchEvent[];
  backend: "supabase" | "memory" | "none";
  error?: string | null;
};

type ResearchBacktestRunSummary = {
  run_id: string | null;
  symbol: string;
  timeframe: string;
  period_days: number;
  status: "done" | "failed" | "skipped";
  candles_tested: number;
  trades: number;
  win_rate: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  profile: string;
  note_th: string;
  error?: string | null;
};

type ResearchBacktestRunResponse = {
  ok: boolean;
  mission_id: string | null;
  runs: ResearchBacktestRunSummary[];
  best_run: ResearchBacktestRunSummary | null;
  message_th: string;
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

export default function ResearchMissionControl() {
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [marketDataHealth, setMarketDataHealth] = useState<MarketDataHealth | null>(null);
  const [mission, setMission] = useState<ResearchMission | null>(null);
  const [researchBacktest, setResearchBacktest] = useState<ResearchBacktestRunResponse | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("พร้อมเริ่มภารกิจวิจัยแบบปลอดเงินจริง");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      const [statusResponse, healthResponse, missionResponse] = await Promise.all([
        fetch(`${apiUrl}/status`, { cache: "no-store" }),
        fetch(`${apiUrl}/market-data-health`, { cache: "no-store" }),
        fetch(`${apiUrl}/research-mission`, { cache: "no-store" })
      ]);

      if (statusResponse.ok) setRuntimeStatus((await statusResponse.json()) as RuntimeStatus);
      if (healthResponse.ok) setMarketDataHealth((await healthResponse.json()) as MarketDataHealth);
      if (missionResponse.ok) setMission((await missionResponse.json()) as ResearchMission);
      if (!statusResponse.ok || !healthResponse.ok || !missionResponse.ok) {
        setError("บาง endpoint ยังไม่ตอบสนอง ลองรีเฟรชอีกครั้งหลัง deploy backend เสร็จ");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูล Mission Control ไม่สำเร็จ");
    }
  }

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 15000);
    return () => window.clearInterval(id);
  }, []);

  const totals = useMemo(() => {
    const candles = marketDataHealth?.candles ?? [];
    return {
      candles: candles.reduce((sum, item) => sum + item.count, 0),
      gaps: candles.reduce((sum, item) => sum + item.gap_count_recent, 0),
      pass: candles.filter((item) => item.status === "pass").length,
      warn: candles.filter((item) => item.status === "warn").length,
      fail: candles.filter((item) => item.status === "fail").length
    };
  }, [marketDataHealth]);

  const matrix = mission?.recommended_plan.backtest_matrix ?? [];
  const rules = mission?.recommended_plan.selection_rules ?? [];

  async function startMission() {
    setBusy(true);
    setMessage("AI กำลังตรวจ safety, ตรวจข้อมูล candles และเลือกแผน backtest...");
    try {
      const response = await fetch(`${apiUrl}/research-mission`, {
        body: JSON.stringify({
          goal: "ทดสอบทุก timeframe เพื่อหาแผน BNBUSDT ที่เหมาะกับ smart money และเตรียม paper simulation",
          symbols: ["BNBUSDT", "BTCUSDT"],
          timeframes: ["1m", "5m", "15m", "1h"],
          max_days: 30,
          include_paper_simulation_plan: true
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      });
      const payload = (await response.json()) as ResearchMission;
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? "เริ่ม AI research mission ไม่สำเร็จ");
      setMission(payload);
      setMessage("AI วางแผนวิจัยแล้ว ขั้นต่อไปคือ Backtest v2 ที่บันทึกผลและ equity curve");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "เริ่มภารกิจไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  async function runReferenceBacktest() {
    setBusy(true);
    setMessage("กำลังรัน legacy backtest 1 วันเพื่อเทียบอ้างอิง ยังไม่ใช่ Backtest v2");
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
      if (!response.ok) throw new Error("รัน backtest อ้างอิงไม่สำเร็จ");
      setBacktestResult((await response.json()) as BacktestResult);
      setMessage("Legacy backtest เสร็จแล้ว ใช้ดูคร่าว ๆ ระหว่างรอ Backtest v2");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backtest ไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  async function runBacktestV2() {
    setBusy(true);
    setMessage("กำลังรัน Backtest v2 จาก Supabase candles และบันทึกผลลงฐานข้อมูล...");
    try {
      const response = await fetch(`${apiUrl}/research-backtests-run`, {
        body: JSON.stringify({
          mission_id: mission?.job_id ?? null,
          max_items: 4,
          starting_balance: 1000,
          min_trades: 5,
          optimize_for_win_rate: true,
          smart_money_priority: true
        }),
        headers: { "content-type": "application/json" },
        method: "POST"
      });
      const payload = (await response.json()) as ResearchBacktestRunResponse;
      if (!response.ok || !payload.ok) throw new Error(payload.message_th ?? "Backtest v2 ไม่สำเร็จ");
      setResearchBacktest(payload);
      setMessage(payload.message_th);
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backtest v2 ไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="labShell">
      <header className="labHeader">
        <div>
          <p className="eyebrow">AI Research Mission Control / Paper-only / Signal-only</p>
          <h1>ห้องควบคุม AI Trading Lab</h1>
          <p className="headerText">
            หน้านี้ออกแบบให้เห็นเป็นขั้นตอนว่า AI กำลังตรวจอะไร เลือกทดสอบอะไร และจะจำลอง trade ด้วยเหตุผลอะไร
            โดยล็อกไว้เป็นงานวิจัยและ paper simulation เท่านั้น ไม่มีการส่งคำสั่งเงินจริง
          </p>
        </div>
        <button className="iconButton" onClick={refresh} title="รีเฟรช" aria-label="รีเฟรช">
          <RefreshCw size={20} />
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
        <StatusCard icon={<ShieldCheck />} label="เงินจริง" value={runtimeStatus?.real_trading ? "เปิด" : "ปิด"} tone={runtimeStatus?.real_trading ? "red" : "green"} />
        <StatusCard icon={<Brain />} label="AI Research" value={runtimeStatus?.ai_research_enabled ? "เปิด" : "รอเปิด"} tone="cyan" />
        <StatusCard icon={<SlidersHorizontal />} label="Auto Strategy" value={runtimeStatus?.ai_auto_strategy_changes ? "เปิด" : "ปิด"} tone={runtimeStatus?.ai_auto_strategy_changes ? "red" : "green"} />
      </section>

      <section className="primaryGrid">
        <div className="panel missionPanel">
          <div className="panelHeader">
            <span>ภารกิจวิจัยล่าสุด</span>
            <strong className={`healthPill ${mission?.status === "failed" ? "fail" : mission?.status === "blocked" ? "warn" : "pass"}`}>
              {mission ? thaiMissionStatus(mission.status) : "ยังไม่มี"}
            </strong>
          </div>
          <div className="missionHero">
            <div>
              <span>เป้าหมาย</span>
              <strong>{mission?.goal ?? "ให้ AI วางแผน backtest ทุก timeframe และเตรียม paper simulation"}</strong>
              <p>{mission?.recommended_plan.safety?.note_th ?? "ระบบยังไม่ให้ AI เปลี่ยน strategy เอง และไม่ใช้เงินจริง"}</p>
            </div>
            <button className="wideButton" onClick={startMission} disabled={busy}>
              {busy ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
              เริ่ม AI วางแผนทดลอง
            </button>
          </div>

          <div className="stepTimeline">
            {(mission?.events ?? defaultEvents()).map((event, index) => (
              <div className={`stepItem ${event.status}`} key={`${event.id ?? event.step}-${index}`}>
                <div className="stepMarker">{index + 1}</div>
                <div>
                  <div className="stepTop">
                    <strong>{event.title_th}</strong>
                    <span>{thaiEventStatus(event.status)}</span>
                  </div>
                  <p>{event.detail_th}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>สถานะข้อมูลตลาด</span>
            <Database size={18} />
          </div>
          <div className="foundationStats twoColumns">
            <Field label="Candles ทั้งหมด" value={totals.candles.toLocaleString()} />
            <Field label="Gap ล่าสุด" value={`${totals.gaps}`} />
            <Field label="ผ่าน" value={`${totals.pass}`} />
            <Field label="เตือน/ผิดปกติ" value={`${totals.warn + totals.fail}`} />
          </div>
          <div className="compactList">
            {(marketDataHealth?.candles ?? []).map((item) => (
              <div className={`compactItem ${item.status}`} key={`${item.symbol}-${item.timeframe}`}>
                <strong>{item.symbol} {item.timeframe}</strong>
                <span>{item.count.toLocaleString()} candles / {formatAge(item.latest_age_seconds)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="researchGrid">
        <div className="panel">
          <div className="panelHeader">
            <span>Backtest Matrix ที่ AI เลือก</span>
            <BarChart3 size={18} />
          </div>
          <div className="matrixGrid">
            {(matrix.length ? matrix : fallbackMatrix()).map((item) => (
              <div className="matrixCard" key={`${item.symbol}-${item.timeframe}`}>
                <div className="matrixTop">
                  <strong>{item.symbol}</strong>
                  <span>{item.timeframe}</span>
                </div>
                <p>{item.purpose}</p>
                <small>{item.days} วัน / {item.execution}</small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>กติกาที่ AI ใช้คัดแผน</span>
            <FlaskConical size={18} />
          </div>
          <div className="ruleList">
            {(rules.length ? rules : fallbackRules()).map((rule) => (
              <div className="ruleItem" key={rule}>
                <CheckCircle2 size={16} />
                <span>{rule}</span>
              </div>
            ))}
          </div>
          <p className="saveState">
            Paper simulation: {mission?.recommended_plan.paper_simulation?.mode ?? "paper_only"} / {mission?.recommended_plan.paper_simulation?.risk ?? "รอผล Backtest v2 ก่อนเริ่มจำลอง"}
          </p>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <span>Backtest v2 และ Paper Research</span>
            <Clock3 size={18} />
          </div>
          <div className="buttonStack">
            <button className="wideButton" onClick={runBacktestV2} disabled={busy}>
              {busy ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
              รัน Backtest v2 จาก Supabase
            </button>
            <button className="wideButton secondary" onClick={runReferenceBacktest} disabled={busy}>
              {busy ? <Activity size={16} className="spinIcon" /> : <Play size={16} />}
              รัน Backtest อ้างอิง 1 วัน
            </button>
          </div>
          <p className="saveState">{message}</p>
          {researchBacktest?.best_run && (
            <div className="bestRun">
              <span>ตัวเต็งสำหรับ paper simulation</span>
              <strong>{researchBacktest.best_run.symbol} {researchBacktest.best_run.timeframe}</strong>
              <p>{researchBacktest.best_run.note_th}</p>
            </div>
          )}
          {researchBacktest?.runs?.length ? (
            <div className="compactList resultList">
              {researchBacktest.runs.map((run) => (
                <div className={`compactItem ${run.status === "done" ? "pass" : run.status === "skipped" ? "warn" : "fail"}`} key={`${run.symbol}-${run.timeframe}-${run.period_days}`}>
                  <strong>{run.symbol} {run.timeframe}</strong>
                  <span>{run.trades} trades / WR {run.win_rate}% / PnL {run.total_pnl_pct}% / DD {run.max_drawdown_pct}%</span>
                </div>
              ))}
            </div>
          ) : null}
          {backtestResult && (
            <div className="foundationStats twoColumns resultStats">
              <Field label="Trades" value={`${backtestResult.trades}`} />
              <Field label="Win Rate" value={`${backtestResult.win_rate}%`} />
              <Field label="PnL" value={`${backtestResult.total_pnl_pct}%`} />
              <Field label="Max DD" value={`${backtestResult.max_drawdown_pct}%`} />
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function StatusCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: "green" | "red" | "amber" | "cyan" }) {
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

function thaiMissionStatus(status: ResearchMission["status"]) {
  return { planned: "วางแผนแล้ว", running: "กำลังทำงาน", done: "เสร็จแล้ว", blocked: "รอเงื่อนไข", failed: "ผิดพลาด" }[status];
}

function thaiEventStatus(status: ResearchEvent["status"]) {
  return { queued: "รอคิว", running: "กำลังทำ", done: "เสร็จ", blocked: "ล็อกไว้", warning: "เตือน" }[status];
}

function formatAge(seconds: number | null) {
  if (seconds === null) return "--";
  if (seconds < 60) return `${seconds} วินาที`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} นาที`;
  return `${Math.round(seconds / 3600)} ชั่วโมง`;
}

function defaultEvents(): ResearchEvent[] {
  const created_at = new Date().toISOString();
  return [
    {
      created_at,
      step: "start",
      status: "queued",
      title_th: "รอเริ่มภารกิจ",
      detail_th: "กดเริ่ม AI วางแผนทดลอง เพื่อให้ระบบตรวจ safety, ตรวจข้อมูล และสร้าง backtest matrix",
      metadata: {}
    }
  ];
}

function fallbackMatrix() {
  return ["1m", "5m", "15m", "1h"].map((timeframe) => ({
    symbol: "BNBUSDT",
    timeframe,
    days: timeframe === "1m" ? 7 : timeframe === "5m" ? 14 : 30,
    purpose: timeframe === "1h" ? "อ่าน regime ใหญ่" : "หา smart money setup และ entry timing",
    execution: "รอ AI mission"
  }));
}

function fallbackRules() {
  return [
    "ไม่ใช้เงินจริง และไม่ส่ง order จริง",
    "ให้ smart money confirmation สำคัญกว่า win rate ดิบ",
    "ดู drawdown, จำนวน trade, fee และ slippage ก่อนเลือกแผน",
    "AI เสนอแผนได้ แต่ยังไม่แก้ strategy อัตโนมัติ"
  ];
}
