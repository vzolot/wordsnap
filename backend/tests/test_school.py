"""M14 регрес: режим школи — ізоляція між викладачами, групи, груповий таргет.
Gated на TEST_DATABASE_URL."""
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.mark.asyncio
async def test_school_isolation_and_groups():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word
    from core.user_service import get_or_create_user
    import core.deck_service as ds
    import core.group_service as gs
    import core.teacher_stats as tstats
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="w", display_name="W"),
                   Tenant(id=2, slug="school", display_name="Школа", is_school=True)])
        await s.commit()

    owner = await get_or_create_user(telegram_id=100, tenant_id=2, first_name="Owner")
    tA = await get_or_create_user(telegram_id=101, tenant_id=2, first_name="TeachA")
    tB = await get_or_create_user(telegram_id=102, tenant_id=2, first_name="TeachB")
    s1 = await get_or_create_user(telegram_id=201, tenant_id=2, first_name="S1")
    s2 = await get_or_create_user(telegram_id=202, tenant_id=2, first_name="S2")
    async with core_db.SessionLocal() as s:
        (await s.execute(select(User).where(User.id == owner.id))).scalar_one().role = "owner"
        await s.commit()
    assert (await gs.add_teacher(2, 101))["ok"]
    assert (await gs.add_teacher(2, 102))["ok"]

    # групи: A має групу з s1, B — з s2
    gA = await gs.create_group(2, "Група A", tA.id)
    gB = await gs.create_group(2, "Група B", tB.id)
    assert await gs.set_group_members(2, gA.id, [s1.id], teacher_user_id=tA.id) == 1
    assert await gs.set_group_members(2, gB.id, [s2.id], teacher_user_id=tB.id) == 1

    # ізоляція: студенти викладача = члени його груп
    assert await gs.student_ids_for_teacher(2, tA.id) == [s1.id]
    assert await gs.student_ids_for_teacher(2, tB.id) == [s2.id]

    # teacher B не може міняти групу teacher A
    assert await gs.set_group_members(2, gA.id, [s2.id], teacher_user_id=tB.id) == -1

    # груповий таргет колоди → матеріалізація лише членам групи
    deck = await ds.create_deck(tenant_id=2, owner_user_id=tA.id, title="ГрупаA-колода",
                                pairs=[("dom", "дім"), ("kot", "кіт")], target_lang="pl",
                                group_id=gA.id)
    async def wc(uid):
        async with core_db.SessionLocal() as s:
            from sqlalchemy import func
            return (await s.execute(select(func.count(Word.id)).where(Word.user_id == uid))).scalar()
    assert await wc(s1.id) == 2 and await wc(s2.id) == 0  # лише s1 (член групи A)

    # дашборд: teacher A бачить лише s1; owner бачить обох
    ovA = await tstats.students_overview(2, restrict_ids=await gs.student_ids_for_teacher(2, tA.id))
    assert {r["id"] for r in ovA} == {s1.id}
    ovOwner = await tstats.students_overview(2)  # owner → без restrict
    assert {r["id"] for r in ovOwner} >= {s1.id, s2.id}

    # deck-list: teacher A бачить лише свою колоду
    decksA = await ds.list_teacher_decks(2, owner_user_id=tA.id)
    decksAll = await ds.list_teacher_decks(2)
    assert len(decksA) == 1 and len(decksAll) >= 1

    # деактивація викладача
    assert await gs.set_teacher_active(2, tB.id, False)
    teachers = await gs.list_teachers(2)
    tb = next(t for t in teachers if t["id"] == tB.id)
    assert tb["is_active"] is False

    await engine.dispose()
