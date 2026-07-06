"""M13 регрес: домашнє завдання — призначення і обчислення статусу."""
import os

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.mark.asyncio
async def test_homework_status():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word
    from core.user_service import get_or_create_user
    import core.deck_service as ds
    import core.homework_service as hs
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="w", display_name="W"), Tenant(id=2, slug="o", display_name="O")])
        await s.commit()

    teacher = await get_or_create_user(telegram_id=500, tenant_id=2)
    student = await get_or_create_user(telegram_id=501, tenant_id=2)
    async with core_db.SessionLocal() as s:
        (await s.execute(select(User).where(User.id == teacher.id))).scalar_one().role = "teacher"
        await s.commit()
    deck = await ds.create_deck(tenant_id=2, owner_user_id=teacher.id, title="D",
                                pairs=[("a", "а"), ("b", "б")], target_lang="pl", assign_to_all=True)

    # призначаємо з майбутнім дедлайном → assigned
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert await hs.assign_homework(2, deck.id, future) == 1
    st = (await hs.list_for_student(2, student.id))[0]
    assert st["status"] == "assigned" and st["total"] == 2 and st["passed"] == 0

    # проходимо 1 слово → in_progress
    async with core_db.SessionLocal() as s:
        w = (await s.execute(select(Word).where(Word.user_id == student.id))).scalars().all()
        w[0].review_count = 1
        await s.commit()
    st = (await hs.list_for_student(2, student.id))[0]
    assert st["status"] == "in_progress" and st["passed"] == 1

    # проходимо всі → done
    async with core_db.SessionLocal() as s:
        for x in (await s.execute(select(Word).where(Word.user_id == student.id))).scalars().all():
            x.review_count = 2
        await s.commit()
    st = (await hs.list_for_student(2, student.id))[0]
    assert st["status"] == "done"

    # прострочений дедлайн + не done → overdue
    past = datetime.now(timezone.utc) - timedelta(days=1)
    async with core_db.SessionLocal() as s:
        for x in (await s.execute(select(Word).where(Word.user_id == student.id))).scalars().all():
            x.review_count = 0
        await s.commit()
    await hs.assign_homework(2, deck.id, past)
    st = (await hs.list_for_student(2, student.id))[0]
    assert st["status"] == "overdue"

    await engine.dispose()
