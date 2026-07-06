"""Календар уроків (white-label M9).

Часові пояси обовʼязково: зберігаємо все в UTC (`lessons.starts_at_utc`),
доступність — у ЛОКАЛЬНІЙ таймзоні викладача (`users.timezone`), показ — у
локальній таймзоні кожного користувача. Слоти генеруються з тижневого шаблону
`teacher_availability`, конвертуються в UTC (з урахуванням DST через ZoneInfo),
і фільтруються від заброньованих/закритих/минулих.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.exc import IntegrityError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import SessionLocal
from .models import (
    Lesson, TeacherAvailability, TeacherClosedDate, Tenant, User,
)

logger = logging.getLogger(__name__)

DEFAULT_DAYS_AHEAD = 14
MIN_BOOK_LEAD_MIN = 60  # не можна бронювати менш ніж за годину до початку


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Europe/Kiev")
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("Europe/Kiev")


async def get_tenant_teacher_id(tenant_id: int) -> int | None:
    """Викладач тенанта (solo-режим — один teacher/owner). Найраніший за id."""
    async with SessionLocal() as s:
        return (await s.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.role.in_(("teacher", "owner")),
            ).order_by(User.id).limit(1)
        )).scalar_one_or_none()


# ─── Доступність (викладач) ──────────────────────────────────────────────────

async def get_availability(tenant_id: int, teacher_user_id: int) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(TeacherAvailability).where(
                TeacherAvailability.tenant_id == tenant_id,
                TeacherAvailability.teacher_user_id == teacher_user_id,
            ).order_by(TeacherAvailability.weekday, TeacherAvailability.start_min)
        )).scalars().all()
        return [
            {"weekday": r.weekday, "start_min": r.start_min, "end_min": r.end_min}
            for r in rows
        ]


async def set_availability(
    tenant_id: int, teacher_user_id: int, slots: list[dict]
) -> int:
    """Повністю замінює тижневий шаблон. slots: [{weekday,start_min,end_min}].
    Валідує 0≤weekday≤6 і 0≤start<end≤1440."""
    clean = []
    for sl in slots or []:
        try:
            wd = int(sl["weekday"]); sm = int(sl["start_min"]); em = int(sl["end_min"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= wd <= 6 and 0 <= sm < em <= 1440:
            clean.append((wd, sm, em))
    async with SessionLocal() as s:
        await s.execute(delete(TeacherAvailability).where(
            TeacherAvailability.tenant_id == tenant_id,
            TeacherAvailability.teacher_user_id == teacher_user_id,
        ))
        for wd, sm, em in clean:
            s.add(TeacherAvailability(
                tenant_id=tenant_id, teacher_user_id=teacher_user_id,
                weekday=wd, start_min=sm, end_min=em,
            ))
        await s.commit()
    return len(clean)


async def get_closed_dates(tenant_id: int, teacher_user_id: int) -> list[str]:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(TeacherClosedDate.day).where(
                TeacherClosedDate.tenant_id == tenant_id,
                TeacherClosedDate.teacher_user_id == teacher_user_id,
            ).order_by(TeacherClosedDate.day)
        )).scalars().all()
        return [d.isoformat() for d in rows]


async def set_date_closed(
    tenant_id: int, teacher_user_id: int, day: date, closed: bool
) -> None:
    async with SessionLocal() as s:
        if closed:
            exists = (await s.execute(
                select(TeacherClosedDate.id).where(
                    TeacherClosedDate.tenant_id == tenant_id,
                    TeacherClosedDate.teacher_user_id == teacher_user_id,
                    TeacherClosedDate.day == day,
                )
            )).scalar_one_or_none()
            if not exists:
                s.add(TeacherClosedDate(
                    tenant_id=tenant_id, teacher_user_id=teacher_user_id, day=day,
                ))
        else:
            await s.execute(delete(TeacherClosedDate).where(
                TeacherClosedDate.tenant_id == tenant_id,
                TeacherClosedDate.teacher_user_id == teacher_user_id,
                TeacherClosedDate.day == day,
            ))
        await s.commit()


# ─── Генерація вільних слотів ────────────────────────────────────────────────

async def free_slots(
    tenant_id: int,
    teacher_user_id: int,
    viewer_tz: str,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
) -> list[dict]:
    """Вільні слоти на next N днів. Час рахуємо у таймзоні викладача, віддаємо
    UTC + локальний час глядача (учня)."""
    async with SessionLocal() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        teacher = (await s.execute(select(User).where(User.id == teacher_user_id))).scalar_one_or_none()
        if tenant is None or teacher is None:
            return []
        duration = tenant.lesson_duration_min or 60
        avail_rows = (await s.execute(
            select(TeacherAvailability).where(
                TeacherAvailability.tenant_id == tenant_id,
                TeacherAvailability.teacher_user_id == teacher_user_id,
            )
        )).scalars().all()
        closed = {d for d in (await s.execute(
            select(TeacherClosedDate.day).where(
                TeacherClosedDate.tenant_id == tenant_id,
                TeacherClosedDate.teacher_user_id == teacher_user_id,
            )
        )).scalars().all()}
        booked = {ts for ts in (await s.execute(
            select(Lesson.starts_at_utc).where(
                Lesson.tenant_id == tenant_id,
                Lesson.teacher_user_id == teacher_user_id,
                Lesson.status == "booked",
            )
        )).scalars().all()}

    if not avail_rows:
        return []
    by_wd: dict[int, list[tuple[int, int]]] = {}
    for r in avail_rows:
        by_wd.setdefault(r.weekday, []).append((r.start_min, r.end_min))

    tz_t = _tz(teacher.timezone)
    tz_v = _tz(viewer_tz)
    now_utc = datetime.now(timezone.utc)
    min_start = now_utc + timedelta(minutes=MIN_BOOK_LEAD_MIN)
    today_local = now_utc.astimezone(tz_t).date()

    out: list[dict] = []
    for off in range(days_ahead + 1):
        d = today_local + timedelta(days=off)
        if d in closed:
            continue
        for (sm, em) in by_wd.get(d.weekday(), []):
            t = sm
            while t + duration <= em:
                local_dt = datetime.combine(d, time(t // 60, t % 60), tzinfo=tz_t)
                utc_dt = local_dt.astimezone(timezone.utc)
                if utc_dt >= min_start and utc_dt not in booked:
                    out.append({
                        "starts_at_utc": utc_dt.isoformat(),
                        "local": utc_dt.astimezone(tz_v).isoformat(),
                        "duration_min": duration,
                    })
                t += duration
    out.sort(key=lambda x: x["starts_at_utc"])
    return out


# ─── Бронювання / скасування ─────────────────────────────────────────────────

async def book_lesson(
    tenant_id: int, teacher_user_id: int, student_user_id: int, starts_at_iso: str,
) -> dict:
    """Бронює слот. Валідує, що слот справді вільний і легальний (є у free_slots),
    потім вставляє з унікальним constraint'ом (гонки → 'slot_taken')."""
    try:
        starts = datetime.fromisoformat(starts_at_iso)
    except ValueError:
        return {"ok": False, "error": "bad_time"}
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=timezone.utc)
    starts = starts.astimezone(timezone.utc)

    # Легальність: слот має бути серед згенерованих вільних (шаблон+не минуле+
    # не закрито+не заброньовано). viewer_tz неважлива для перевірки UTC-збігу.
    slots = await free_slots(tenant_id, teacher_user_id, "UTC")
    valid = {datetime.fromisoformat(s["starts_at_utc"]) for s in slots}
    if starts not in valid:
        return {"ok": False, "error": "slot_unavailable"}

    async with SessionLocal() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        lesson = Lesson(
            tenant_id=tenant_id,
            teacher_user_id=teacher_user_id,
            student_user_id=student_user_id,
            starts_at_utc=starts,
            duration_min=(tenant.lesson_duration_min if tenant else 60),
            status="booked",
        )
        s.add(lesson)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            return {"ok": False, "error": "slot_taken"}  # хтось встиг раніше
        await s.refresh(lesson)
        return {"ok": True, "lesson_id": lesson.id, "starts_at_utc": starts.isoformat()}


async def cancel_lesson(tenant_id: int, lesson_id: int, by_user_id: int) -> dict:
    """Скасовує урок. Скасувати можуть учень або викладач цього уроку, не
    пізніше ніж за cancel_cutoff_hours до початку (для викладача — без обмеження)."""
    async with SessionLocal() as s:
        lesson = (await s.execute(
            select(Lesson).where(Lesson.id == lesson_id, Lesson.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if lesson is None or lesson.status != "booked":
            return {"ok": False, "error": "not_found"}
        is_teacher = lesson.teacher_user_id == by_user_id
        is_student = lesson.student_user_id == by_user_id
        if not (is_teacher or is_student):
            return {"ok": False, "error": "forbidden"}
        if is_student:
            tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
            cutoff_h = tenant.cancel_cutoff_hours if tenant else 12
            if lesson.starts_at_utc - datetime.now(timezone.utc) < timedelta(hours=cutoff_h):
                return {"ok": False, "error": "too_late", "cutoff_hours": cutoff_h}
        lesson.status = "cancelled"
        await s.commit()
        return {"ok": True, "starts_at_utc": lesson.starts_at_utc.isoformat(),
                "student_user_id": lesson.student_user_id,
                "teacher_user_id": lesson.teacher_user_id}


async def list_lessons(
    tenant_id: int, *, student_user_id: int | None = None,
    teacher_user_id: int | None = None, upcoming_only: bool = True,
) -> list[dict]:
    async with SessionLocal() as s:
        q = select(Lesson).where(Lesson.tenant_id == tenant_id, Lesson.status == "booked")
        if student_user_id is not None:
            q = q.where(Lesson.student_user_id == student_user_id)
        if teacher_user_id is not None:
            q = q.where(Lesson.teacher_user_id == teacher_user_id)
        if upcoming_only:
            q = q.where(Lesson.starts_at_utc >= datetime.now(timezone.utc) - timedelta(hours=1))
        rows = (await s.execute(q.order_by(Lesson.starts_at_utc))).scalars().all()
        # імена учнів (для викладацького списку)
        student_ids = {r.student_user_id for r in rows}
        names = {}
        if student_ids:
            for u in (await s.execute(select(User).where(User.id.in_(student_ids)))).scalars().all():
                names[u.id] = (u.first_name or (f"@{u.username}" if u.username else f"id{u.telegram_id}"))
        return [
            {
                "id": r.id,
                "starts_at_utc": r.starts_at_utc.isoformat(),
                "duration_min": r.duration_min,
                "student_user_id": r.student_user_id,
                "student_name": names.get(r.student_user_id),
                "teacher_user_id": r.teacher_user_id,
            }
            for r in rows
        ]
