"""M5 регрес: колоди викладача — парсинг, матеріалізація, дописування без
скидання прогресу, ізоляція адресатів. Gated на TEST_DATABASE_URL (як
test_isolation). Один тест-корутин (патч core.db до імпорту сервісів)."""
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


def test_parse_word_pairs_formats():
    # чистий unit — без БД
    import sys
    sys.path  # noqa
    from core.deck_service import parse_word_pairs
    pairs = parse_word_pairs("hola - привіт\nadios — бувай\ngato\tкіт\nsi;так\nno,ні\nсміття")
    assert [p[0] for p in pairs] == ["hola", "adios", "gato", "si", "no"]


@pytest.mark.asyncio
async def test_deck_materialization_no_reset_and_isolation():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word
    from core.user_service import get_or_create_user
    from core.word_service import process_review
    import core.deck_service as ds

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="wordsnap", display_name="W"),
                   Tenant(id=2, slug="oksana", display_name="O")])
        await s.commit()

    async def wc(uid):
        async with core_db.SessionLocal() as s:
            return (await s.execute(select(func.count(Word.id)).where(Word.user_id == uid))).scalar()

    teacher = await get_or_create_user(telegram_id=500, tenant_id=2)
    s1 = await get_or_create_user(telegram_id=501, tenant_id=2)
    s2 = await get_or_create_user(telegram_id=502, tenant_id=2)

    deck = await ds.create_deck(
        tenant_id=2, owner_user_id=teacher.id, title="D",
        pairs=ds.parse_word_pairs("\n".join(f"w{i} - п{i}" for i in range(15))),
        target_lang="pl", assign_to_all=True)
    assert await wc(s1.id) == 15 and await wc(s2.id) == 15

    async with core_db.SessionLocal() as s:
        wid = (await s.execute(select(Word.id).where(Word.user_id == s1.id).limit(1))).scalar()
    await process_review(wid, "knew", user_id=s1.id)

    added = await ds.add_words_to_deck(deck.id, 2, ds.parse_word_pairs("\n".join(f"x{i} - y{i}" for i in range(5))))
    assert added == 5
    assert await wc(s1.id) == 20 and await wc(s2.id) == 20
    async with core_db.SessionLocal() as s:
        rc = (await s.execute(select(func.sum(Word.review_count)).where(Word.user_id == s1.id))).scalar()
    assert rc == 1, "old progress was reset!"  # 1 review збережено

    # персональна колода — лише s1
    await ds.create_deck(tenant_id=2, owner_user_id=teacher.id, title="P",
                         pairs=ds.parse_word_pairs("secret - таємниця"),
                         target_lang="pl", assign_to_all=False, assignee_user_ids=[s1.id])
    assert await wc(s1.id) == 21 and await wc(s2.id) == 20

    await engine.dispose()
