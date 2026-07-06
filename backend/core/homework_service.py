"""Домашнє завдання з дедлайном (M13). Викладач призначає «пройти колоду до
дати». Статус обчислюється динамічно: done = усі слова колоди (матеріалізовані
цьому учню) пройдені хоча б раз (review_count>0); overdue = не done і дедлайн
минув; in_progress = є прогрес; assigned = ще нічого.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import Deck, Homework, Word


async def _progress(session, deck_id: int, user_id: int) -> tuple[int, int]:
    """(passed, total) слів колоди, матеріалізованих цьому учню."""
    total = (await session.execute(
        select(func.count(Word.id)).where(
            Word.user_id == user_id, Word.deck_id == deck_id,
        )
    )).scalar() or 0
    passed = (await session.execute(
        select(func.count(Word.id)).where(
            Word.user_id == user_id, Word.deck_id == deck_id, Word.review_count > 0,
        )
    )).scalar() or 0
    return int(passed), int(total)


def _status(passed: int, total: int, due_at: datetime, now: datetime) -> str:
    if total > 0 and passed >= total:
        return "done"
    if due_at < now:
        return "overdue"
    if passed > 0:
        return "in_progress"
    return "assigned"


async def assign_homework(
    tenant_id: int, deck_id: int, due_at_utc: datetime, user_ids: list[int] | None = None,
) -> int:
    """Створює/оновлює ДЗ для адресатів колоди (або заданих user_ids). Повертає
    кількість призначених. Валідує, що колода належить тенанту."""
    async with SessionLocal() as s:
        deck = (await s.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            raise ValueError("deck_not_found")
        if user_ids is None:
            # усі, кому матеріалізована колода
            user_ids = list((await s.execute(
                select(Word.user_id).where(Word.deck_id == deck_id).distinct()
            )).scalars().all())
        n = 0
        for uid in user_ids:
            stmt = pg_insert(Homework).values(
                tenant_id=tenant_id, deck_id=deck_id, user_id=uid,
                due_at_utc=due_at_utc, status="assigned",
            ).on_conflict_do_update(
                index_elements=["deck_id", "user_id"],
                set_={"due_at_utc": due_at_utc, "status": "assigned", "reminder_sent": False},
            )
            await s.execute(stmt)
            n += 1
        await s.commit()
        return n


async def list_for_student(tenant_id: int, user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(Homework, Deck.title).join(Deck, Deck.id == Homework.deck_id).where(
                Homework.tenant_id == tenant_id, Homework.user_id == user_id,
            ).order_by(Homework.due_at_utc)
        )).all()
        out = []
        for hw, title in rows:
            passed, total = await _progress(s, hw.deck_id, user_id)
            out.append({
                "id": hw.id, "deck_id": hw.deck_id, "title": title,
                "due_at_utc": hw.due_at_utc.isoformat(),
                "passed": passed, "total": total,
                "status": _status(passed, total, hw.due_at_utc, now),
            })
        return out


async def status_for(tenant_id: int, deck_id: int, user_id: int) -> dict | None:
    """Статус ДЗ для конкретного (deck, user) — для дайджесту M10."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as s:
        hw = (await s.execute(
            select(Homework).where(
                Homework.tenant_id == tenant_id,
                Homework.deck_id == deck_id, Homework.user_id == user_id,
            )
        )).scalar_one_or_none()
        if hw is None:
            return None
        passed, total = await _progress(s, deck_id, user_id)
        return {
            "deck_id": deck_id, "due_at_utc": hw.due_at_utc.isoformat(),
            "passed": passed, "total": total,
            "status": _status(passed, total, hw.due_at_utc, now),
        }


async def student_homework_summary(tenant_id: int, user_id: int) -> list[dict]:
    """Короткий підсумок ДЗ учня для передурочного дайджесту викладачу."""
    return [
        {"title": h["title"], "status": h["status"], "passed": h["passed"], "total": h["total"]}
        for h in await list_for_student(tenant_id, user_id)
    ]
