"""M9 регрес: календар — генерація слотів (TZ), бронювання, анти-подвійне
бронювання, дедлайн скасування. Gated на TEST_DATABASE_URL. Один тест-корутин."""
import os

import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.mark.asyncio
async def test_calendar_slots_booking_and_cancel():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Lesson
    from core.user_service import get_or_create_user
    import core.calendar_service as cal
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
        await c.execute(text("CREATE UNIQUE INDEX uq_lessons_teacher_slot "
                             "ON lessons(tenant_id, teacher_user_id, starts_at_utc) WHERE status='booked'"))
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="w", display_name="W"), Tenant(id=2, slug="o", display_name="O")])
        await s.commit()

    teacher = await get_or_create_user(telegram_id=500, tenant_id=2)
    student = await get_or_create_user(telegram_id=501, tenant_id=2)
    async with core_db.SessionLocal() as s:
        (await s.execute(select(User).where(User.id == teacher.id))).scalar_one().role = "teacher"
        (await s.execute(select(User).where(User.id == teacher.id))).scalar_one().timezone = "Europe/Warsaw"
        (await s.execute(select(User).where(User.id == student.id))).scalar_one().timezone = "America/New_York"
        await s.commit()

    tomorrow = (datetime.now(ZoneInfo("Europe/Warsaw")) + timedelta(days=1)).date()
    await cal.set_availability(2, teacher.id, [{"weekday": tomorrow.weekday(), "start_min": 600, "end_min": 720}])

    slots = await cal.free_slots(2, teacher.id, "America/New_York")
    tmr = [s for s in slots if datetime.fromisoformat(s["starts_at_utc"]).astimezone(ZoneInfo("Europe/Warsaw")).date() == tomorrow]
    assert len(tmr) == 2
    # TZ: Warsaw 10:00 і локальний час учня узгоджені
    u = datetime.fromisoformat(tmr[0]["starts_at_utc"])
    assert u.astimezone(ZoneInfo("Europe/Warsaw")).hour == 10
    assert u.astimezone(ZoneInfo("America/New_York")) == datetime.fromisoformat(tmr[0]["local"])

    # booking
    r = await cal.book_lesson(2, teacher.id, student.id, tmr[0]["starts_at_utc"])
    assert r["ok"]
    r2 = await cal.book_lesson(2, teacher.id, student.id, tmr[0]["starts_at_utc"])
    assert r2["ok"] is False  # уже зайнято/недоступно

    # double-booking DB constraint
    from sqlalchemy.exc import IntegrityError
    blocked = False
    try:
        async with core_db.SessionLocal() as s:
            s.add(Lesson(tenant_id=2, teacher_user_id=teacher.id, student_user_id=student.id,
                         starts_at_utc=datetime.fromisoformat(tmr[0]["starts_at_utc"]), status="booked"))
            await s.commit()
    except IntegrityError:
        blocked = True
    assert blocked

    # cancel cutoff: <12h → too_late for student, teacher ok
    async with core_db.SessionLocal() as s:
        soon = Lesson(tenant_id=2, teacher_user_id=teacher.id, student_user_id=student.id,
                      starts_at_utc=datetime.now(timezone.utc) + timedelta(hours=2), status="booked")
        s.add(soon); await s.commit(); await s.refresh(soon)
        soon_id = soon.id
    assert (await cal.cancel_lesson(2, soon_id, by_user_id=student.id))["error"] == "too_late"
    assert (await cal.cancel_lesson(2, soon_id, by_user_id=teacher.id))["ok"]

    await engine.dispose()
