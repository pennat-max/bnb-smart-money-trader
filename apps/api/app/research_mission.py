from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from .collector import supabase_rest_headers
from .config import Settings
from .market_data_repository import candle_health, market_data_health
from .models import ResearchEvent, ResearchMissionRequest, ResearchMissionResponse

logger = logging.getLogger(__name__)


def table_url(settings: Settings, table: str) -> str | None:
    if not settings.supabase_url:
        return None
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def build_research_plan(settings: Settings, request: ResearchMissionRequest) -> dict[str, Any]:
    plan_items = []
    for symbol in request.symbols:
        for timeframe in request.timeframes:
            days = min(request.max_days, recommended_days_for_timeframe(timeframe))
            plan_items.append(
                {
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "days": days,
                    "purpose": purpose_for_timeframe(timeframe),
                    "execution": "queued_for_backtest_v2",
                }
            )

    primary = [item for item in plan_items if item["symbol"] == "BNBUSDT"]
    return {
        "objective": request.goal,
        "safety": {
            "app_mode": settings.app_mode,
            "real_trading": False,
            "auto_strategy_changes": settings.ai_auto_strategy_changes,
            "note_th": "ระบบนี้วิจัยและจำลองเท่านั้น ยังไม่ส่ง order จริง และไม่เปลี่ยน strategy อัตโนมัติ",
        },
        "backtest_matrix": plan_items,
        "priority_order": primary + [item for item in plan_items if item["symbol"] != "BNBUSDT"],
        "selection_rules": [
            "ให้ความสำคัญกับ smart money confirmation ก่อน win rate ดิบ",
            "ตัดแผนที่ drawdown สูงหรือจำนวน trade น้อยเกินไป",
            "เทียบ 15m กับ 1h เพื่อดู trend/regime ก่อนจำลอง paper",
            "เป้าหมาย 1% ต่อวันเป็น benchmark ไม่ใช่การการันตีผล",
        ],
        "paper_simulation": {
            "enabled_after_human_review": True,
            "mode": "paper_only",
            "risk": "เริ่ม risk ต่ำ และหยุดเมื่อ daily loss แตะ 2%",
        },
    }


def recommended_days_for_timeframe(timeframe: str) -> int:
    return {"1m": 7, "5m": 14, "15m": 30, "1h": 60}.get(timeframe, 30)


def purpose_for_timeframe(timeframe: str) -> str:
    return {
        "1m": "หา entry timing และ fake breakout ระยะสั้น",
        "5m": "ตรวจ stop hunt และ liquidity sweep ที่เกิดบ่อย",
        "15m": "ใช้เป็น timeframe หลักสำหรับ setup คุณภาพ",
        "1h": "อ่าน market regime และ bias ใหญ่",
    }.get(timeframe, "วิจัยตลาด")


def build_events(settings: Settings, request: ResearchMissionRequest, plan: dict[str, Any]) -> list[ResearchEvent]:
    now = datetime.now(timezone.utc)
    health = market_data_health(settings)
    data_status = str(health.get("status", "warn"))
    events = [
        ResearchEvent(
            created_at=now,
            step="safety_check",
            status="done",
            title_th="ตรวจ safety lock",
            detail_th=f"APP_MODE={settings.app_mode}, real_trading=false, AI auto strategy changes={settings.ai_auto_strategy_changes}. ไม่มีการส่ง order จริง",
            metadata={"app_mode": settings.app_mode, "real_trading": False},
        ),
        ResearchEvent(
            created_at=now,
            step="data_health",
            status="done" if data_status == "pass" else "warning",
            title_th="ตรวจฐานข้อมูล candles",
            detail_th=f"Market data health = {data_status}. ใช้ข้อมูลนี้เป็นฐานก่อนเลือก backtest matrix",
            metadata={"health": health},
        ),
        ResearchEvent(
            created_at=now,
            step="planner",
            status="done",
            title_th="AI เลือกแผนทดสอบ",
            detail_th=f"เลือกทดสอบ {len(plan['backtest_matrix'])} ชุด จาก symbols/timeframes ที่กำหนด โดยให้ smart money confirmation มาก่อนการไล่ win rate",
            metadata={"backtest_count": len(plan["backtest_matrix"])},
        ),
        ResearchEvent(
            created_at=now,
            step="backtest_queue",
            status="queued",
            title_th="รอ Backtest v2",
            detail_th="เฟสถัดไปจะรันจาก Supabase candles, บันทึกผล run/trades/equity curve และแสดงความคืบหน้าแบบ realtime",
            metadata={"items": plan["priority_order"][:8]},
        ),
        ResearchEvent(
            created_at=now,
            step="paper_simulation",
            status="blocked",
            title_th="ยังไม่เริ่ม paper simulation อัตโนมัติ",
            detail_th="ต้องมีผล Backtest v2 ที่ผ่านเงื่อนไขก่อน แล้วจึงจำลอง paper-only โดยยังไม่ใช้เงินจริง",
            metadata={"requires": ["backtest_v2_results", "human_review"]},
        ),
    ]

    for symbol in request.symbols:
        for timeframe in request.timeframes:
            check = candle_health(settings, symbol, timeframe, recent_limit=100)
            events.append(
                ResearchEvent(
                    created_at=now,
                    step=f"candle_{symbol.upper()}_{timeframe}",
                    status="done" if check["status"] == "pass" else "warning",
                    title_th=f"ตรวจ {symbol.upper()} {timeframe}",
                    detail_th=f"พบ {check['count']} candles, gap ล่าสุด {check.get('gap_count_recent', 0)}, สถานะ {check['status']}",
                    metadata=check,
                )
            )
    return events


async def create_research_mission(settings: Settings, request: ResearchMissionRequest) -> ResearchMissionResponse:
    if not settings.ai_research_enabled:
        return ResearchMissionResponse(
            ok=False,
            status="blocked",
            goal=request.goal,
            recommended_plan={},
            events=[],
            error="AI_RESEARCH_ENABLED is false.",
        )

    plan = build_research_plan(settings, request)
    events = build_events(settings, request, plan)
    job_id, backend, error = await save_mission(settings, request, plan, events)
    return ResearchMissionResponse(
        ok=error is None,
        job_id=job_id,
        status="planned" if error is None else "failed",
        auto_strategy_changes=settings.ai_auto_strategy_changes,
        goal=request.goal,
        recommended_plan=plan,
        events=[event.model_copy(update={"job_id": job_id}) for event in events],
        backend=backend,
        error=error,
    )


async def save_mission(
    settings: Settings,
    request: ResearchMissionRequest,
    plan: dict[str, Any],
    events: list[ResearchEvent],
) -> tuple[str | None, str, str | None]:
    headers = supabase_rest_headers(settings)
    jobs_url = table_url(settings, "research_jobs")
    events_url = table_url(settings, "research_events")
    if headers is None or jobs_url is None or events_url is None:
        local_id = str(uuid4())
        return local_id, "memory", "Supabase is not configured; mission was generated in memory only."

    job_payload = {
        "status": "planned",
        "mode": "research_only",
        "goal": request.goal,
        "symbols": [symbol.upper() for symbol in request.symbols],
        "timeframes": request.timeframes,
        "max_days": request.max_days,
        "real_trading": False,
        "auto_strategy_changes": settings.ai_auto_strategy_changes,
        "recommended_plan": plan,
        "summary_th": "AI สร้างแผนวิจัยแล้ว รอ Backtest v2 และ paper simulation แบบปลอดเงินจริง",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            job_response = await client.post(
                jobs_url,
                json=job_payload,
                headers={**headers, "Prefer": "return=representation"},
            )
            job_response.raise_for_status()
            job_rows = job_response.json()
            job_id = job_rows[0]["id"]
            event_payloads = [
                {
                    "job_id": job_id,
                    "step": event.step,
                    "status": event.status,
                    "title_th": event.title_th,
                    "detail_th": event.detail_th,
                    "metadata": event.metadata,
                }
                for event in events
            ]
            event_response = await client.post(
                events_url,
                json=event_payloads,
                headers={**headers, "Prefer": "return=minimal"},
            )
            event_response.raise_for_status()
        return job_id, "supabase", None
    except Exception as exc:
        logger.exception("Research mission save failed")
        return None, "none", str(exc)


async def latest_research_mission(settings: Settings) -> ResearchMissionResponse:
    headers = supabase_rest_headers(settings)
    jobs_url = table_url(settings, "research_jobs")
    if headers is None or jobs_url is None:
        return ResearchMissionResponse(
            ok=False,
            status="blocked",
            goal="ยังไม่มี mission",
            recommended_plan={},
            events=[],
            backend="none",
            error="Supabase is not configured.",
        )

    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(jobs_url, params=params, headers=headers)
            response.raise_for_status()
            rows = response.json()
        if not rows:
            return ResearchMissionResponse(
                ok=True,
                status="planned",
                goal="ยังไม่มี mission",
                recommended_plan={},
                events=[],
                backend="supabase",
            )
        job = rows[0]
        events = await fetch_research_events(settings, job["id"])
        return ResearchMissionResponse(
            ok=True,
            job_id=job["id"],
            status=job["status"],
            auto_strategy_changes=bool(job.get("auto_strategy_changes", False)),
            goal=job["goal"],
            recommended_plan=job.get("recommended_plan") or {},
            events=events,
            backend="supabase",
        )
    except Exception as exc:
        logger.exception("Research mission fetch failed")
        return ResearchMissionResponse(
            ok=False,
            status="failed",
            goal="โหลด mission ไม่สำเร็จ",
            recommended_plan={},
            events=[],
            backend="none",
            error=str(exc),
        )


async def fetch_research_events(settings: Settings, job_id: str) -> list[ResearchEvent]:
    headers = supabase_rest_headers(settings)
    events_url = table_url(settings, "research_events")
    if headers is None or events_url is None:
        return []
    params = {
        "job_id": f"eq.{job_id}",
        "select": "*",
        "order": "created_at.asc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(events_url, params=params, headers=headers)
        response.raise_for_status()
        rows = response.json()
    return [
        ResearchEvent(
            id=row.get("id"),
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
            job_id=row.get("job_id"),
            step=row["step"],
            status=row["status"],
            title_th=row["title_th"],
            detail_th=row["detail_th"],
            metadata=row.get("metadata") or {},
        )
        for row in rows
    ]
