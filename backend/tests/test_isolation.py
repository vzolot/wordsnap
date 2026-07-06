"""Тести ізоляції даних між тенантами (white-label M4).

Потребують реальний Postgres — задаються через TEST_DATABASE_URL. Без нього
пропускаються (щоб дефолтний pure-logic CI не залежав від БД):

    TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/wordsnap_iso \
        python -m pytest tests/test_isolation.py -q

Один тест-корутин навмисно: сервіси роблять `from .db import SessionLocal` на
імпорті, тож патч core.db має статися ДО їх імпорту і з єдиним engine у одному
event loop — інакше asyncpg скаржиться на «operation in progress»/чужий loop.

Перевіряємо: (а) учень тенанта A не бачить колод B; (б) учень X не бачить
персональних колод Y всередині тенанта; + скоуп user-резолву, words/reviews,
leaderboard, save_word.tenant_id, безлімітність white-label.
"""
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest.mark.asyncio
async def test_tenant_isolation_end_to_end():
    # Патч core.db ДО імпорту сервісів (вони роблять from .db import SessionLocal).
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word, Review, Deck, DeckAssignment
    from core.user_service import get_or_create_user, can_add_word
    from core.word_service import save_word, process_review
    from core.deck_service import get_visible_decks
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)
    S = core_db.SessionLocal

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with S() as s:
        s.add_all([
            Tenant(id=1, slug="wordsnap", display_name="WordSnap",
                   ai_snap_monthly_limit=None, billing_ui_enabled=True),
            Tenant(id=2, slug="oksana", display_name="Слова з Оксаною"),
        ])
        await s.commit()

    # ── (1) той самий telegram_id у 2 тенантів = 2 незалежні профілі ──
    a = await get_or_create_user(telegram_id=777, tenant_id=1, first_name="A")
    b = await get_or_create_user(telegram_id=777, tenant_id=2, first_name="A")
    assert a.id != b.id and a.tenant_id == 1 and b.tenant_id == 2
    assert (await get_or_create_user(telegram_id=777, tenant_id=1)).id == a.id  # не дублюємо

    # ── (2) words/reviews скоупляться по тенанту ──
    ai = {"translation": "привіт"}
    await save_word(user_id=a.id, word="hi", target_lang="en", ai_data=ai, tenant_id=a.tenant_id)
    await save_word(user_id=b.id, word="hi", target_lang="en", ai_data=ai, tenant_id=b.tenant_id)
    async with S() as s:
        wa = (await s.execute(select(Word).where(Word.user_id == a.id))).scalars().all()
        wb = (await s.execute(select(Word).where(Word.user_id == b.id))).scalars().all()
    assert len(wa) == 1 and wa[0].tenant_id == 1
    assert len(wb) == 1 and wb[0].tenant_id == 2
    await process_review(wb[0].id, "knew", user_id=b.id)
    async with S() as s:
        rev = (await s.execute(select(Review).where(Review.user_id == b.id))).scalars().one()
    assert rev.tenant_id == 2  # review успадкував tenant слова

    # ── (3) leaderboard скоуп: тенант-1 борд не включає тенант-2 ──
    async def set_xp(u, xp):
        async with S() as s:
            uu = (await s.execute(select(User).where(User.id == u.id))).scalars().one()
            uu.target_lang = "en"; uu.total_xp = xp; uu.show_on_leaderboard = True
            await s.commit()
    c = await get_or_create_user(telegram_id=3, tenant_id=2)
    await set_xp(a, 100); await set_xp(c, 999)
    async with S() as s:
        board_t1 = (await s.execute(
            select(func.count(User.id)).where(
                User.tenant_id == 1, User.target_lang == "en",
                User.total_xp > 0, User.show_on_leaderboard.is_(True),
            )
        )).scalar()
    assert board_t1 == 1  # лише 'a' з тенанта 1, не 'c' з тенанта 2

    # ── (4) видимість колод: (а) крос-тенант, (б) персональні інших учнів ──
    x = await get_or_create_user(telegram_id=10, tenant_id=1)
    y = await get_or_create_user(telegram_id=11, tenant_id=1)
    z = await get_or_create_user(telegram_id=12, tenant_id=2)
    async with S() as s:
        d_all_t1 = Deck(tenant_id=1, title="Всім-1", assign_to_all=True)
        d_pers_y = Deck(tenant_id=1, title="Персональна-Y", assign_to_all=False)
        d_all_t2 = Deck(tenant_id=2, title="Всім-2", assign_to_all=True)
        s.add_all([d_all_t1, d_pers_y, d_all_t2])
        await s.commit()
        await s.refresh(d_pers_y)
        s.add(DeckAssignment(deck_id=d_pers_y.id, user_id=y.id))
        await s.commit()
    x_decks = {d.title for d in await get_visible_decks(x.id, 1)}
    y_decks = {d.title for d in await get_visible_decks(y.id, 1)}
    z_decks = {d.title for d in await get_visible_decks(z.id, 2)}
    assert x_decks == {"Всім-1"}, x_decks                       # не бачить персональну Y і тенант-2
    assert y_decks == {"Всім-1", "Персональна-Y"}, y_decks      # бачить свою персональну
    assert z_decks == {"Всім-2"}, z_decks                       # інший тенант ізольований

    # ── (5) white-label без ліміту на слова ──
    z.target_lang = "en"
    ok, _ = await can_add_word(z)
    assert ok is True

    await engine.dispose()
