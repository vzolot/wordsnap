"""API календаря уроків (white-label M9).

Викладацькі ендпоінти — під `_require_teacher`. Учнівські — під загальним
initData-middleware (будь-який користувач тенанта). Час зберігається в UTC,
показ — у локальній таймзоні користувача. Підтвердження бронювання/скасування
йде ОБОМ (учню і викладачу) з бота відповідного тенанта.
"""
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from zoneinfo import ZoneInfo

from core.db import SessionLocal
from core.models import Tenant, User
from core import calendar_service as cal
from core.telegram_send import send_message
from webhook.teacher_routes import _require_teacher

logger = logging.getLogger(__name__)
router = APIRouter()


async def _user(telegram_id: int, tenant_id: int) -> User | None:
    async with SessionLocal() as s:
        return (await s.execute(
            select(User).where(User.telegram_id == telegram_id, User.tenant_id == tenant_id)
        )).scalar_one_or_none()


def _fmt(iso: str, tz_name: str) -> str:
    """UTC-iso → людський локальний рядок 'Пн 12.05 14:00'."""
    dt = datetime.fromisoformat(iso).astimezone(ZoneInfo(tz_name))
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"][dt.weekday()]
    return f"{wd} {dt.strftime('%d.%m %H:%M')}"


async def _notify_lesson(tenant_id: int, teacher_id: int, student_id: int,
                         starts_iso: str, kind: str) -> None:
    """Шле підтвердження обом сторонам у їх локальному часі з бота тенанта."""
    async with SessionLocal() as s:
        users = {u.id: u for u in (await s.execute(
            select(User).where(User.id.in_([teacher_id, student_id]))
        )).scalars().all()}
    teacher = users.get(teacher_id)
    student = users.get(student_id)
    verb = {"booked": "заброньовано", "cancelled": "скасовано"}.get(kind, kind)
    emoji = "📅" if kind == "booked" else "❌"
    if teacher:
        when = _fmt(starts_iso, teacher.timezone or "Europe/Kiev")
        sname = (student.first_name if student else None) or "учень"
        await send_message(teacher.telegram_id,
                           f"{emoji} Урок {verb}: <b>{when}</b> — {sname}",
                           tenant_id=tenant_id)
    if student:
        when = _fmt(starts_iso, student.timezone or "Europe/Kiev")
        await send_message(student.telegram_id,
                           f"{emoji} Твій урок {verb}: <b>{when}</b>",
                           tenant_id=tenant_id)


# ─── Викладач ────────────────────────────────────────────────────────────────

class AvailabilityRequest(BaseModel):
    slots: list[dict]  # [{weekday,start_min,end_min}]


class ClosedDateRequest(BaseModel):
    day: str          # 'YYYY-MM-DD'
    closed: bool = True


@router.get("/api/teacher/availability")
async def get_availability(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    teacher = await _require_teacher(telegram_id, tenant_id)
    async with SessionLocal() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
    return {
        "availability": await cal.get_availability(tenant_id, teacher.id),
        "closed_dates": await cal.get_closed_dates(tenant_id, teacher.id),
        "timezone": teacher.timezone or "Europe/Kiev",
        "lesson_duration_min": tenant.lesson_duration_min,
        "cancel_cutoff_hours": tenant.cancel_cutoff_hours,
    }


@router.put("/api/teacher/availability")
async def put_availability(
    data: AvailabilityRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    n = await cal.set_availability(tenant_id, teacher.id, data.slots)
    return {"ok": True, "slots": n}


@router.post("/api/teacher/closed_date")
async def post_closed_date(
    data: ClosedDateRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    try:
        day = date.fromisoformat(data.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad_day")
    await cal.set_date_closed(tenant_id, teacher.id, day, data.closed)
    return {"ok": True}


@router.get("/api/teacher/lessons")
async def teacher_lessons(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    teacher = await _require_teacher(telegram_id, tenant_id)
    lessons = await cal.list_lessons(tenant_id, teacher_user_id=teacher.id)
    return {"lessons": lessons, "timezone": teacher.timezone or "Europe/Kiev"}


@router.post("/api/teacher/lessons/{lesson_id}/cancel")
async def teacher_cancel(
    lesson_id: int, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    r = await cal.cancel_lesson(tenant_id, lesson_id, by_user_id=teacher.id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["error"])
    await _notify_lesson(tenant_id, r["teacher_user_id"], r["student_user_id"],
                         r["starts_at_utc"], "cancelled")
    return {"ok": True}


# ─── Учень ───────────────────────────────────────────────────────────────────

class BookRequest(BaseModel):
    starts_at_utc: str


@router.get("/api/calendar/slots")
async def calendar_slots(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    """Вільні слоти викладача тенанта, у локальному часі учня."""
    user = await _user(telegram_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    teacher_id = await cal.get_tenant_teacher_id(tenant_id)
    if teacher_id is None:
        return {"slots": [], "timezone": user.timezone or "Europe/Kiev", "has_teacher": False}
    slots = await cal.free_slots(tenant_id, teacher_id, user.timezone or "Europe/Kiev")
    return {"slots": slots, "timezone": user.timezone or "Europe/Kiev", "has_teacher": True}


@router.get("/api/calendar/my")
async def my_lessons(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    user = await _user(telegram_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    lessons = await cal.list_lessons(tenant_id, student_user_id=user.id)
    return {"lessons": lessons, "timezone": user.timezone or "Europe/Kiev"}


@router.post("/api/calendar/book")
async def calendar_book(
    data: BookRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    user = await _user(telegram_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    teacher_id = await cal.get_tenant_teacher_id(tenant_id)
    if teacher_id is None:
        raise HTTPException(status_code=400, detail="no_teacher")
    r = await cal.book_lesson(tenant_id, teacher_id, user.id, data.starts_at_utc)
    if not r["ok"]:
        raise HTTPException(status_code=409, detail=r["error"])
    await _notify_lesson(tenant_id, teacher_id, user.id, r["starts_at_utc"], "booked")
    return {"ok": True, "lesson_id": r["lesson_id"]}


@router.post("/api/calendar/lessons/{lesson_id}/cancel")
async def calendar_cancel(
    lesson_id: int, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    user = await _user(telegram_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    r = await cal.cancel_lesson(tenant_id, lesson_id, by_user_id=user.id)
    if not r["ok"]:
        raise HTTPException(status_code=400, detail=r["error"])
    await _notify_lesson(tenant_id, r["teacher_user_id"], r["student_user_id"],
                         r["starts_at_utc"], "cancelled")
    return {"ok": True}
