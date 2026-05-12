from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .collector import supabase_rest_headers
from .config import Settings
from .journal import recent_signals
from .learning import summarize_learning
from .models import AICommitteeReport, AIProviderReport, AIReportRequest, PaperTradeRecord
from .paper import load_paper_trades


def configured_ai_providers(settings: Settings) -> list[str]:
    providers = []
    if settings.deepseek_api_key:
        providers.append("deepseek")
    if settings.gemini_api_key:
        providers.append("gemini")
    if settings.groq_api_key:
        providers.append("groq")
    if settings.openai_api_key:
        providers.append("openai")
    return providers


async def generate_ai_committee_report(settings: Settings, request: AIReportRequest) -> AICommitteeReport:
    paper_trades = load_paper_trades(settings, limit=500)
    signals = recent_signals(settings, limit=120)
    snapshots = fetch_market_snapshots(settings, limit=120)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=request.hours)
    scoped_trades = [trade for trade in paper_trades if trade.updated_at >= cutoff]
    scoped_signals = [row for row in signals if parse_time(row.get("created_at")) >= cutoff]
    scoped_snapshots = [row for row in snapshots if parse_time(row.get("created_at")) >= cutoff]
    learning = summarize_learning([], scoped_trades)
    context = build_analysis_context(settings, request, scoped_trades, scoped_signals, scoped_snapshots, learning)
    provider_reports = await run_committee(settings, request, context)
    return build_consensus(settings, request, context, provider_reports)


def fetch_market_snapshots(settings: Settings, limit: int = 100) -> list[dict]:
    headers = supabase_rest_headers(settings)
    if headers is None or not settings.supabase_url:
        return []
    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/market_snapshots"
    params = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_time(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def build_analysis_context(
    settings: Settings,
    request: AIReportRequest,
    trades: list[PaperTradeRecord],
    signals: list[dict],
    snapshots: list[dict],
    learning: dict[str, float | int | str],
) -> dict:
    closed = [trade for trade in trades if trade.status == "CLOSED"]
    open_trades = [trade for trade in trades if trade.status == "OPEN"]
    signal_counts = Counter(str(row.get("signal", "UNKNOWN")) for row in signals)
    detection_counts: Counter[str] = Counter()
    for row in signals:
        detections = row.get("detections") or {}
        if isinstance(detections, str):
            try:
                detections = json.loads(detections)
            except Exception:
                detections = {}
        for key, value in detections.items():
            if value:
                detection_counts[key] += 1
    latest_snapshot = snapshots[0] if snapshots else {}
    total_pnl = round(sum(trade.pnl_pct for trade in closed), 3)
    estimated_pnl_usdt = round(sum(trade.pnl_usdt for trade in closed), 4)
    return {
        "mode": "paper_only_signal_only",
        "hours": request.hours,
        "daily_target_pct": settings.risk_daily_target_pct,
        "paper_starting_balance": settings.paper_starting_balance,
        "paper_trades": {
            "total": len(trades),
            "closed": len(closed),
            "open": len(open_trades),
            "pnl_pct": total_pnl,
            "pnl_usdt": estimated_pnl_usdt,
            "learning": learning,
            "recent_closed": [trade.model_dump(mode="json") for trade in closed[-20:]],
        },
        "signals": {
            "total": len(signals),
            "counts": dict(signal_counts),
            "top_detections": detection_counts.most_common(12),
            "recent": signals[:20],
        },
        "market_snapshots": {
            "total": len(snapshots),
            "latest": latest_snapshot,
            "recent_context": [
                {
                    "created_at": row.get("created_at"),
                    "price": row.get("price"),
                    "open_interest_change_pct": row.get("open_interest_change_pct"),
                    "bid_ask_imbalance": row.get("bid_ask_imbalance"),
                    "liquidation_imbalance": row.get("liquidation_imbalance"),
                    "mtf_alignment_score": row.get("mtf_alignment_score"),
                    "market_context": row.get("market_context"),
                }
                for row in snapshots[:30]
            ],
        },
        "hard_rules": [
            "Do not place real orders.",
            "Signal-only and paper-only analysis.",
            "Daily target is a benchmark, not a guarantee.",
            "Prefer survival and lower drawdown over forcing trades.",
        ],
    }


async def run_committee(settings: Settings, request: AIReportRequest, context: dict) -> list[AIProviderReport]:
    provider_order = [
        settings.ai_primary_provider,
        settings.ai_secondary_provider,
        settings.ai_fast_provider,
    ]
    if request.include_premium:
        provider_order.append(settings.ai_premium_provider)

    reports: list[AIProviderReport] = []
    seen: set[str] = set()
    for provider in provider_order:
        normalized = provider.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        reports.append(await run_provider(settings, normalized, context))

    if not reports:
        reports.append(rule_based_provider_report(context))
    return reports


async def run_provider(settings: Settings, provider: str, context: dict) -> AIProviderReport:
    model = provider_model(settings, provider)
    if not provider_key(settings, provider):
        return AIProviderReport(
            provider=provider,
            model=model,
            ok=False,
            skipped=True,
            summary=f"{provider} skipped: API key is not configured.",
        )
    try:
        if provider == "gemini":
            return await call_gemini(settings, context)
        return await call_openai_compatible(settings, provider, context)
    except Exception as exc:
        return AIProviderReport(
            provider=provider,
            model=model,
            ok=False,
            summary=f"{provider} failed; rule-based report will still be used.",
            error=str(exc)[:300],
        )


def provider_key(settings: Settings, provider: str) -> str | None:
    return {
        "deepseek": settings.deepseek_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "openai": settings.openai_api_key,
    }.get(provider)


def provider_model(settings: Settings, provider: str) -> str:
    return {
        "deepseek": settings.deepseek_model,
        "gemini": settings.gemini_model,
        "groq": settings.groq_model,
        "openai": settings.openai_model,
    }.get(provider, "unknown")


async def call_openai_compatible(settings: Settings, provider: str, context: dict) -> AIProviderReport:
    base_urls = {
        "deepseek": "https://api.deepseek.com/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
    }
    key = provider_key(settings, provider)
    model = provider_model(settings, provider)
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": analyst_system_prompt()},
            {"role": "user", "content": json.dumps(compact_context(context, provider), ensure_ascii=False)},
        ],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(base_urls[provider], json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return provider_report_from_json(provider, model, content)


async def call_gemini(settings: Settings, context: dict) -> AIProviderReport:
    model = settings.gemini_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": analyst_system_prompt() + "\n\nDATA:\n" + json.dumps(compact_context(context, "gemini"), ensure_ascii=False)}],
            }
        ],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
        response.raise_for_status()
        content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return provider_report_from_json("gemini", model, content)


def analyst_system_prompt() -> str:
    return (
        "You are an AI risk analyst for a BNBUSDT paper-trading system. "
        "Analyze only; never recommend placing real orders. "
        "Return JSON with keys: summary, confidence_adjustment, risk_adjustment, recommended_filters. "
        "summary must be simple Thai mixed with English trading terms. "
        "confidence_adjustment is an integer from -10 to 10. "
        "risk_adjustment is one of: reduce, keep, increase_carefully. "
        "recommended_filters is an array of short strings."
    )


def compact_context(context: dict, provider: str) -> dict:
    if provider == "gemini":
        return context

    signals = context.get("signals", {})
    snapshots = context.get("market_snapshots", {})
    compacted = {
        **context,
        "signals": {
            "total": signals.get("total", 0),
            "counts": signals.get("counts", {}),
            "top_detections": signals.get("top_detections", [])[:10],
            "recent": [
                {
                    "created_at": row.get("created_at"),
                    "signal": row.get("signal"),
                    "confidence": row.get("confidence"),
                    "risk_score": row.get("risk_score"),
                    "price": row.get("price"),
                    "detections": row.get("detections"),
                }
                for row in signals.get("recent", [])[:10]
            ],
        },
        "market_snapshots": {
            "total": snapshots.get("total", 0),
            "latest": snapshots.get("latest", {}),
            "recent_context": snapshots.get("recent_context", [])[:10],
        },
    }
    if provider == "groq":
        compacted["signals"]["recent"] = compacted["signals"]["recent"][:5]
        compacted["market_snapshots"]["recent_context"] = compacted["market_snapshots"]["recent_context"][:5]
        compacted["paper_trades"]["recent_closed"] = compacted["paper_trades"].get("recent_closed", [])[-5:]
    return compacted


def provider_report_from_json(provider: str, model: str, content: str) -> AIProviderReport:
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"summary": content}
    return AIProviderReport(
        provider=provider,
        model=model,
        ok=True,
        summary=str(parsed.get("summary", ""))[:2000],
        confidence_adjustment=int(parsed.get("confidence_adjustment", 0) or 0),
        risk_adjustment=str(parsed.get("risk_adjustment", "keep")),
        recommended_filters=[str(item) for item in parsed.get("recommended_filters", [])[:8]]
        if isinstance(parsed.get("recommended_filters", []), list)
        else [],
    )


def rule_based_provider_report(context: dict) -> AIProviderReport:
    learning = context["paper_trades"]["learning"]
    win_rate = float(learning.get("win_rate", 0))
    pnl = float(context["paper_trades"]["pnl_pct"])
    if context["paper_trades"]["closed"] < 5:
        summary = "ข้อมูล paper ยังน้อย ให้เก็บตัวอย่างต่อก่อน อย่าเพิ่ม risk และอย่าฝืนเป้า 1%."
        adjustment = 0
        risk = "keep"
        filters = ["wait for more paper samples", "keep confidence >= 70"]
    elif pnl < 0 or win_rate < 45:
        summary = "ผล paper ยังอ่อน ควรเข้ม confidence และรอ smart money confirmation เพิ่ม."
        adjustment = -5
        risk = "reduce"
        filters = ["require MTF alignment", "avoid low volume z-score", "avoid mixed VWAP signals"]
    else:
        summary = "ผล paper เริ่มใช้ได้ แต่ยังควรคุม drawdown และเพิ่ม risk แบบช้ามากเท่านั้น."
        adjustment = 2
        risk = "keep"
        filters = ["keep paper-only", "compare 15m vs 1h trend"]
    return AIProviderReport(
        provider="rule_based",
        model="local",
        ok=True,
        summary=summary,
        confidence_adjustment=adjustment,
        risk_adjustment=risk,
        recommended_filters=filters,
    )


def build_consensus(
    settings: Settings,
    request: AIReportRequest,
    context: dict,
    provider_reports: list[AIProviderReport],
) -> AICommitteeReport:
    active_reports = [report for report in provider_reports if report.ok and not report.skipped]
    if not active_reports:
        active_reports = [rule_based_provider_report(context)]
        provider_reports.extend(active_reports)
    average_adjustment = sum(report.confidence_adjustment for report in active_reports) / len(active_reports)
    learning = context["paper_trades"]["learning"]
    pnl = float(context["paper_trades"]["pnl_pct"])
    target = settings.risk_daily_target_pct * (request.hours / 24)
    progress = (pnl / target) if target else 0
    consensus_score = max(0, min(100, int(50 + average_adjustment * 4 + progress * 20)))
    target_status = "ahead" if pnl >= target else "behind" if pnl < 0 else "building"
    lessons = sorted({item for report in active_reports for item in report.recommended_filters})[:8]
    if not lessons:
        lessons = ["collect more paper samples", "keep signal-only mode"]
    adjustments = [
        f"confidence adjustment vote: {round(average_adjustment, 2)}",
        f"risk vote: {Counter(report.risk_adjustment for report in active_reports).most_common(1)[0][0]}",
        "do not enable real trading from this report",
    ]
    return AICommitteeReport(
        created_at=datetime.now(timezone.utc),
        hours=request.hours,
        providers_used=[report.provider for report in active_reports],
        providers_skipped=[report.provider for report in provider_reports if report.skipped],
        consensus_score=consensus_score,
        paper_pnl_pct=pnl,
        estimated_pnl_usdt=float(context["paper_trades"]["pnl_usdt"]),
        win_rate=float(learning.get("win_rate", 0)),
        samples=int(learning.get("samples", 0)),
        daily_target_pct=settings.risk_daily_target_pct,
        target_status=target_status,
        consensus_summary_th=build_summary_text(pnl, target, active_reports),
        lessons_learned=lessons,
        strategy_adjustments=adjustments,
        safety_notes=[
            "Paper-only analysis.",
            "No real orders are placed.",
            "1% daily target is a benchmark, not a guarantee.",
        ],
        provider_reports=provider_reports,
    )


def build_summary_text(pnl: float, target: float, reports: list[AIProviderReport]) -> str:
    lead = "AI Committee สรุป: "
    if pnl >= target:
        lead += "paper PnL นำหน้า benchmark ตอนนี้ "
    elif pnl < 0:
        lead += "paper PnL ติดลบ ควรลดความ aggressive "
    else:
        lead += "paper PnL ยังต่ำกว่าเป้า แต่ยังอยู่ในช่วงเก็บข้อมูล "
    summaries = " | ".join(report.summary for report in reports[:3] if report.summary)
    return (lead + summaries)[:2500]
