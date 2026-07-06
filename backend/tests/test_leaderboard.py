"""M16 регрес: тижневий лідерборд — ранжування, анти-накрутка, self-rank."""
import os

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.mark.asyncio
async def test_weekly_leaderboard():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word, Review
    from core.user_service import get_or_create_user
    import core.deck_service as ds
    import core.leaderboard_service as lb
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="w", display_name="W"), Tenant(id=2, slug="o", display_name="O")])
        await s.commit()

    teacher = await get_or_create_user(telegram_id=500, tenant_id=2)
    a = await get_or_create_user(telegram_id=501, tenant_id=2, first_name="A")
    b = await get_or_create_user(telegram_id=502, tenant_id=2, first_name="B")
    async with core_db.SessionLocal() as s:
        (await s.execute(select(User).where(User.id == teacher.id))).scalar_one().role = "teacher"
        await s.commit()
    deck = await ds.create_deck(tenant_id=2, owner_user_id=teacher.id, title="D",
                                pairs=[("x", "х"), ("y", "y")], target_lang="pl", assign_to_all=True)

    since, until = lb.current_week_bounds()
    mid = since + timedelta(hours=1)
    async with core_db.SessionLocal() as s:
        wa = (await s.execute(select(Word).where(Word.user_id == a.id))).scalars().all()
        wb = (await s.execute(select(Word).where(Word.user_id == b.id))).scalars().all()
        # A: 2 різні слова (2 бали); B: те саме слово 5 разів того ж дня (анти-накрутка → 1 бал)
        s.add(Review(user_id=a.id, word_id=wa[0].id, tenant_id=2, result="knew", reviewed_at=mid))
        s.add(Review(user_id=a.id, word_id=wa[1].id, tenant_id=2, result="knew", reviewed_at=mid))
        for _ in range(5):
            s.add(Review(user_id=b.id, word_id=wb[0].id, tenant_id=2, result="knew", reviewed_at=mid))
        await s.commit()

    board = await lb.group_leaderboard(2)
    assert board["total"] == 2
    top = board["rows"]
    assert top[0]["user_id"] == a.id and top[0]["reviews"] == 2   # A перший
    b_row = next(r for r in top if r["user_id"] == b.id)
    assert b_row["reviews"] == 1, "анти-накрутка: 5 тапів по 1 слову = 1 бал"
    assert board["all_ranks"][a.id] == 1 and board["all_ranks"][b.id] == 2

    await engine.dispose()
