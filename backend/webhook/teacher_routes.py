"""API режиму викладача (white-label M5). Усі ендпоінти:
  • під /api/ → проходять initData-middleware (telegram_id+tenant_id довірені);
  • вимагають role='teacher'|'owner' І збіг тенанта (перевірка _require_teacher).
Колоди/учні строго в межах тенанта викладача.
"""
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from core import analytics
from core.db import SessionLocal
from core.models import User
from core import deck_service as ds

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_teacher(telegram_id: int, tenant_id: int) -> User:
    """Резолвить юзера в межах тенанта і вимагає роль teacher/owner. Інакше 403."""
    async with SessionLocal() as session:
        user = (await session.execute(
            select(User).where(
                User.telegram_id == telegram_id,
                User.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    if user.role not in ("teacher", "owner"):
        raise HTTPException(status_code=403, detail="not_a_teacher")
    return user


class DeckCreateRequest(BaseModel):
    title: str
    target_lang: str | None = None
    text: str = ""                       # «слово - переклад» по рядку або CSV
    assign_to_all: bool = True
    assignee_user_ids: list[int] | None = None


class DeckPatchRequest(BaseModel):
    add_text: str | None = None          # дописати слова
    remove_word_ids: list[int] | None = None
    assignee_user_ids: list[int] | None = None  # перепризначити (для персональних)


@router.get("/api/teacher/decks")
async def teacher_list_decks(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    await _require_teacher(telegram_id, tenant_id)
    return {"decks": await ds.list_teacher_decks(tenant_id)}


@router.get("/api/teacher/students")
async def teacher_list_students(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    await _require_teacher(telegram_id, tenant_id)
    return {"students": await ds.list_tenant_students(tenant_id)}


@router.get("/api/teacher/decks/{deck_id}")
async def teacher_deck_detail(
    deck_id: int, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    await _require_teacher(telegram_id, tenant_id)
    detail = await ds.get_deck_detail(deck_id, tenant_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="deck_not_found")
    return detail


@router.post("/api/teacher/decks")
async def teacher_create_deck(
    data: DeckCreateRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    title = (data.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title_required")
    pairs = ds.parse_word_pairs(data.text or "")
    if not pairs:
        raise HTTPException(status_code=400, detail="no_valid_pairs")
    deck = await ds.create_deck(
        tenant_id=tenant_id,
        owner_user_id=teacher.id,
        title=title,
        pairs=pairs,
        target_lang=(data.target_lang or teacher.target_lang),
        assign_to_all=bool(data.assign_to_all),
        assignee_user_ids=data.assignee_user_ids,
    )
    analytics.capture(telegram_id, "teacher_deck_created", {
        "tenant_id": tenant_id,
        "deck_id": deck.id,
        "word_count": len(pairs),
        "assign_to_all": bool(data.assign_to_all),
        "assignees": len(data.assignee_user_ids or []) if not data.assign_to_all else None,
    })
    return {"ok": True, "deck_id": deck.id, "word_count": len(pairs)}


@router.patch("/api/teacher/decks/{deck_id}")
async def teacher_update_deck(
    deck_id: int, data: DeckPatchRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    await _require_teacher(telegram_id, tenant_id)
    result: dict = {"ok": True}

    if data.add_text:
        pairs = ds.parse_word_pairs(data.add_text)
        if pairs:
            try:
                added = await ds.add_words_to_deck(deck_id, tenant_id, pairs)
            except ValueError:
                raise HTTPException(status_code=404, detail="deck_not_found")
            result["added_words"] = added

    if data.remove_word_ids:
        removed = 0
        for wid in data.remove_word_ids:
            if await ds.remove_deck_word(deck_id, tenant_id, wid):
                removed += 1
        result["removed_words"] = removed

    if data.assignee_user_ids is not None:
        try:
            result["assignees"] = await ds.set_deck_assignees(
                deck_id, tenant_id, data.assignee_user_ids
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="deck_not_found")

    analytics.capture(telegram_id, "teacher_deck_updated", {
        "tenant_id": tenant_id, "deck_id": deck_id,
        "added": result.get("added_words", 0),
        "removed": result.get("removed_words", 0),
    })
    return result
