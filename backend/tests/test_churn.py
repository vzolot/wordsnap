"""M12 регрес: алерти ризику відтоку — вибір неактивних + анти-спам cooldown."""
import os

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


class FakeBot:
    def __init__(self, bot_id):
        self.id = bot_id
        self.sent = []
    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text})


@pytest.mark.asyncio
async def test_churn_alert_selection_and_cooldown():
    os.environ.setdefault("DATABASE_URL", TEST_DB.replace("+asyncpg", ""))
    import core.db as core_db
    engine = create_async_engine(TEST_DB, echo=False)
    core_db.engine = engine
    core_db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    from core.models import Base, Tenant, User, Word, Review
    from core.user_service import get_or_create_user
    import core.deck_service as ds
    import core.bot_registry as reg
    import scheduler.churn_alert as churn
    from tests.conftest import bind_test_engine
    bind_test_engine(core_db.SessionLocal)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with core_db.SessionLocal() as s:
        s.add_all([Tenant(id=1, slug="w", display_name="W"),
                   Tenant(id=2, slug="o", display_name="O", churn_alert_days=5)])
        await s.commit()

    teacher = await get_or_create_user(telegram_id=500, tenant_id=2, first_name="T")
    inactive = await get_or_create_user(telegram_id=501, tenant_id=2, first_name="Inactive")
    active = await get_or_create_user(telegram_id=502, tenant_id=2, first_name="Active")
    async with core_db.SessionLocal() as s:
        (await s.execute(select(User).where(User.id == teacher.id))).scalar_one().role = "teacher"
        await s.commit()
    deck = await ds.create_deck(tenant_id=2, owner_user_id=teacher.id, title="D",
                                pairs=[("a", "а")], target_lang="pl", assign_to_all=True)
    now = datetime.now(timezone.utc)
    async with core_db.SessionLocal() as s:
        wi = (await s.execute(select(Word).where(Word.user_id == inactive.id))).scalars().all()[0]
        wa = (await s.execute(select(Word).where(Word.user_id == active.id))).scalars().all()[0]
        s.add(Review(user_id=inactive.id, word_id=wi.id, tenant_id=2, result="knew",
                     reviewed_at=now - timedelta(days=10)))  # 10 днів тому → в ризику
        s.add(Review(user_id=active.id, word_id=wa.id, tenant_id=2, result="knew",
                     reviewed_at=now - timedelta(days=1)))   # вчора → ок
        await s.commit()

    fake = FakeBot(2000002)
    reg.register(2, fake)

    await churn.check_churn(FakeBot(999))
    msgs = [m for m in fake.sent if m["chat_id"] == teacher.telegram_id]
    assert len(msgs) == 1 and "Inactive" in msgs[0]["text"]
    assert "Active" not in " ".join(m["text"] for m in msgs)

    # анти-спам: повторний прогін нічого не шле (cooldown 7 днів)
    fake.sent.clear()
    await churn.check_churn(FakeBot(999))
    assert not fake.sent

    await engine.dispose()
