"""Сервіс колод (white-label). Тут — інваріант видимості колод учню, який
є критичним для ізоляції даних. Повний CRUD викладача — M5.

Правило видимості (учень бачить):
  • колоди СВОГО тенанта з assign_to_all = true, ПЛЮС
  • колоди свого тенанта, персонально призначені йому (deck_assignments).
Колоди інших тенантів і персональні колоди інших учнів — невидимі.
"""
from __future__ import annotations

from sqlalchemy import select, exists, and_

from .db import SessionLocal
from .models import Deck, DeckAssignment


def visible_decks_stmt(user_id: int, tenant_id: int):
    """SELECT-стейтмент видимих учню колод (для перевикористання/тестів)."""
    assigned = exists().where(
        and_(
            DeckAssignment.deck_id == Deck.id,
            DeckAssignment.user_id == user_id,
        )
    )
    return (
        select(Deck)
        .where(
            Deck.tenant_id == tenant_id,
            (Deck.assign_to_all.is_(True)) | assigned,
        )
        .order_by(Deck.created_at.desc())
    )


async def get_visible_decks(user_id: int, tenant_id: int) -> list[Deck]:
    """Колоди, видимі цьому учню (у межах його тенанта)."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            visible_decks_stmt(user_id, tenant_id)
        )).scalars().all()
        return list(rows)
