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
from core import teacher_stats as tstats
from core.rate_limit import allow as _rl_allow

logger = logging.getLogger(__name__)

# Ліміт завантаження колод: захист від випадкового спаму парсера (цикл на
# клієнті). Щедрий для нормального викладача, але ловить розбіг.
_DECK_WRITE_LIMIT = 30      # операцій запису колод
_DECK_WRITE_WINDOW = 60.0   # за 60 секунд на викладача

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


async def _require_owner(telegram_id: int, tenant_id: int) -> User:
    user = await _require_teacher(telegram_id, tenant_id)
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="not_an_owner")
    return user


async def _school_scope(teacher: User, tenant_id: int) -> tuple[list[int] | None, int | None]:
    """(restrict_student_ids, deck_owner_id) для ізоляції в школі. owner і
    solo-режим → (None, None) = бачить усе. Викладач у школі → лише свої."""
    from core.group_service import is_school, student_ids_for_teacher
    if teacher.role == "owner":
        return None, None
    if await is_school(tenant_id):
        return await student_ids_for_teacher(tenant_id, teacher.id), teacher.id
    return None, None


class DeckCreateRequest(BaseModel):
    title: str
    target_lang: str | None = None
    text: str = ""                       # «слово - переклад» по рядку або CSV
    assign_to_all: bool = True
    assignee_user_ids: list[int] | None = None
    group_id: int | None = None          # M14: адресувати групі (school-режим)


class DeckPatchRequest(BaseModel):
    add_text: str | None = None          # дописати слова
    remove_word_ids: list[int] | None = None
    assignee_user_ids: list[int] | None = None  # перепризначити (для персональних)


@router.get("/api/teacher/decks")
async def teacher_list_decks(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    teacher = await _require_teacher(telegram_id, tenant_id)
    _, deck_owner = await _school_scope(teacher, tenant_id)
    return {"decks": await ds.list_teacher_decks(tenant_id, owner_user_id=deck_owner)}


@router.get("/api/teacher/students")
async def teacher_list_students(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    """Дашборд учнів з агрегатами (стрік, 7д повторень, останній візит, %
    вивчених, ризик). Неактивні зверху. Містить id+display_name — тому годиться
    і як пікер адресатів у формі створення колоди. У школі викладач бачить лише
    своїх учнів (owner — усіх)."""
    teacher = await _require_teacher(telegram_id, tenant_id)
    restrict, _ = await _school_scope(teacher, tenant_id)
    return {"students": await tstats.students_overview(tenant_id, restrict_ids=restrict)}


@router.get("/api/teacher/students/{student_id}")
async def teacher_student_detail(
    student_id: int, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Детальний прогрес учня: активність 7/30д, прогрес по колодах, слабкі слова."""
    await _require_teacher(telegram_id, tenant_id)
    detail = await tstats.student_detail(tenant_id, student_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="student_not_found")
    return detail


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
    if not _rl_allow(f"deckwrite:{tenant_id}:{telegram_id}", _DECK_WRITE_LIMIT, _DECK_WRITE_WINDOW):
        raise HTTPException(status_code=429, detail="rate_limited")
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
        group_id=data.group_id,
    )
    analytics.capture(telegram_id, "teacher_deck_created", {
        "tenant_id": tenant_id,
        "deck_id": deck.id,
        "word_count": len(pairs),
        "assign_to_all": bool(data.assign_to_all),
        "assignees": len(data.assignee_user_ids or []) if not data.assign_to_all else None,
    })
    return {"ok": True, "deck_id": deck.id, "word_count": len(pairs)}


class HomeworkRequest(BaseModel):
    due_at_utc: str                    # ISO час дедлайну
    user_ids: list[int] | None = None  # None → усі адресати колоди


@router.post("/api/teacher/decks/{deck_id}/homework")
async def teacher_assign_homework(
    deck_id: int, data: HomeworkRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """M13: призначити ДЗ «пройти колоду до дати» адресатам колоди."""
    from datetime import datetime, timezone
    from core import homework_service as hw
    await _require_teacher(telegram_id, tenant_id)
    try:
        due = datetime.fromisoformat(data.due_at_utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad_due")
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    try:
        n = await hw.assign_homework(tenant_id, deck_id, due, data.user_ids)
    except ValueError:
        raise HTTPException(status_code=404, detail="deck_not_found")
    analytics.capture(telegram_id, "teacher_homework_assigned", {
        "tenant_id": tenant_id, "deck_id": deck_id, "students": n,
    })
    return {"ok": True, "assigned": n}


class DeckFromPhotoRequest(BaseModel):
    image_b64: str            # base64 без data-URL префіксу
    image_mime: str = "image/jpeg"


@router.post("/api/teacher/decks/from_photo")
async def teacher_deck_from_photo(
    data: DeckFromPhotoRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """M11: фото сторінки → пари «слово–переклад» (превʼю для редагування).
    Рахує виклик у ai_snap_usage тенанта і поважає місячний ліміт. НЕ зберігає
    колоду — повертає пари, які викладач редагує і зберігає через POST /decks."""
    from core.openai_client import extract_word_pairs_from_image
    from core.tenant_service import get_tenant_by_id, ai_snap_available, incr_ai_snap_usage

    teacher = await _require_teacher(telegram_id, tenant_id)
    if not _rl_allow(f"deckwrite:{tenant_id}:{telegram_id}", _DECK_WRITE_LIMIT, _DECK_WRITE_WINDOW):
        raise HTTPException(status_code=429, detail="rate_limited")

    tenant = await get_tenant_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    if not await ai_snap_available(tenant):
        # Мʼяко: ліміт AI-снапу вичерпано цього місяця.
        raise HTTPException(status_code=429, detail="ai_snap_limit_reached")

    b64 = (data.image_b64 or "").strip()
    if not b64:
        raise HTTPException(status_code=400, detail="no_image")
    pairs = await extract_word_pairs_from_image(
        b64, target_lang=(teacher.target_lang or "en"),
        native_lang=(teacher.native_lang or "uk"), image_mime=data.image_mime,
    )
    # Рахуємо виклик навіть якщо пар мало — це реальний OpenAI-запит.
    await incr_ai_snap_usage(tenant_id)
    analytics.capture(telegram_id, "teacher_deck_photo_extracted", {
        "tenant_id": tenant_id, "pairs": len(pairs),
    })
    return {"ok": True, "pairs": pairs}


@router.patch("/api/teacher/decks/{deck_id}")
async def teacher_update_deck(
    deck_id: int, data: DeckPatchRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    await _require_teacher(telegram_id, tenant_id)
    if not _rl_allow(f"deckwrite:{tenant_id}:{telegram_id}", _DECK_WRITE_LIMIT, _DECK_WRITE_WINDOW):
        raise HTTPException(status_code=429, detail="rate_limited")
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


# ─── Режим школи (M14): викладачі та групи ───────────────────────────────────

class AddTeacherRequest(BaseModel):
    telegram_id: int


class TeacherActiveRequest(BaseModel):
    active: bool


class GroupCreateRequest(BaseModel):
    name: str


class GroupMembersRequest(BaseModel):
    user_ids: list[int]


@router.get("/api/teacher/school")
async def school_info(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    """Чи це школа + роль поточного користувача (для UI owner/teacher)."""
    from core.group_service import is_school
    teacher = await _require_teacher(telegram_id, tenant_id)
    return {"is_school": await is_school(tenant_id), "role": teacher.role}


@router.get("/api/teacher/teachers")
async def list_teachers(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    await _require_owner(telegram_id, tenant_id)
    from core.group_service import list_teachers as _lt
    return {"teachers": await _lt(tenant_id)}


@router.post("/api/teacher/teachers")
async def add_teacher(data: AddTeacherRequest, telegram_id: int = Query(...), tenant_id: int = Query(1)):
    await _require_owner(telegram_id, tenant_id)
    from core.group_service import add_teacher as _at
    r = await _at(tenant_id, data.telegram_id)
    if not r["ok"]:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.post("/api/teacher/teachers/{teacher_user_id}/active")
async def set_teacher_active(
    teacher_user_id: int, data: TeacherActiveRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    await _require_owner(telegram_id, tenant_id)
    from core.group_service import set_teacher_active as _sa
    ok = await _sa(tenant_id, teacher_user_id, data.active)
    if not ok:
        raise HTTPException(status_code=404, detail="teacher_not_found")
    return {"ok": True}


@router.get("/api/teacher/groups")
async def list_groups(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    teacher = await _require_teacher(telegram_id, tenant_id)
    from core.group_service import list_groups as _lg
    # owner бачить усі групи; викладач — лише свої.
    scope = None if teacher.role == "owner" else teacher.id
    return {"groups": await _lg(tenant_id, teacher_user_id=scope)}


@router.post("/api/teacher/groups")
async def create_group(data: GroupCreateRequest, telegram_id: int = Query(...), tenant_id: int = Query(1)):
    teacher = await _require_teacher(telegram_id, tenant_id)
    from core.group_service import create_group as _cg
    g = await _cg(tenant_id, data.name, teacher.id)
    return {"ok": True, "group_id": g.id}


@router.put("/api/teacher/groups/{group_id}/members")
async def set_group_members(
    group_id: int, data: GroupMembersRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    from core.group_service import set_group_members as _sm
    scope = None if teacher.role == "owner" else teacher.id
    n = await _sm(tenant_id, group_id, data.user_ids, teacher_user_id=scope)
    if n < 0:
        raise HTTPException(status_code=403, detail="not_your_group")
    return {"ok": True, "members": n}
