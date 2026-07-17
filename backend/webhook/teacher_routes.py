"""API режиму викладача (white-label M5). Усі ендпоінти:
  • під /api/ → проходять initData-middleware (telegram_id+tenant_id довірені);
  • вимагають role='teacher'|'owner' І збіг тенанта (перевірка _require_teacher).
Колоди/учні строго в межах тенанта викладача.
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from core import analytics
from core.db import SessionLocal
from core.models import Tenant, User
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


async def _school_scope(
    teacher: User, tenant_id: int, as_teacher: bool = False,
) -> tuple[list[int] | None, int | None]:
    """(restrict_student_ids, deck_owner_id) для ізоляції в школі. Соло-режим →
    (None, None) = бачить усе. Викладач у школі → лише свої. owner-адмін бачить
    усе, АЛЕ коли перемкнувся в «режим викладача» (as_teacher) — теж лише своє."""
    from core.group_service import is_school, student_ids_for_teacher
    if not await is_school(tenant_id):
        return None, None
    if teacher.role == "owner" and not as_teacher:
        return None, None
    return await student_ids_for_teacher(tenant_id, teacher.id), teacher.id


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
async def teacher_list_decks(
    telegram_id: int = Query(...), tenant_id: int = Query(1),
    as_teacher: bool = Query(False),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    _, deck_owner = await _school_scope(teacher, tenant_id, as_teacher=as_teacher)
    return {"decks": await ds.list_teacher_decks(tenant_id, owner_user_id=deck_owner)}


@router.get("/api/teacher/students")
async def teacher_list_students(
    telegram_id: int = Query(...), tenant_id: int = Query(1),
    as_teacher: bool = Query(False),
):
    """Дашборд учнів з агрегатами (стрік, 7д повторень, останній візит, %
    вивчених, ризик). Неактивні зверху. Містить id+display_name — тому годиться
    і як пікер адресатів у формі створення колоди. У школі викладач бачить лише
    своїх учнів (owner — усіх)."""
    teacher = await _require_teacher(telegram_id, tenant_id)
    restrict, _ = await _school_scope(teacher, tenant_id, as_teacher=as_teacher)
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
    # Переклад НЕОБОВʼЯЗКОВИЙ: рядок «лише слово» → автопереклад через AI.
    entries = ds.parse_deck_entries(data.text or "")
    if not entries:
        raise HTTPException(status_code=400, detail="no_valid_pairs")
    deck_target = (data.target_lang or teacher.target_lang or "en")
    pairs = await ds.autofill_translations(
        entries, target_lang=deck_target, native_lang=(teacher.native_lang or "uk"),
    )
    deck = await ds.create_deck(
        tenant_id=tenant_id,
        owner_user_id=teacher.id,
        title=title,
        pairs=pairs,
        target_lang=deck_target,
        assign_to_all=bool(data.assign_to_all),
        assignee_user_ids=data.assignee_user_ids,
        group_id=data.group_id,
    )
    # Сповіщаємо учнів-адресатів про нову колоду (best-effort).
    try:
        await ds.notify_students_new_words(tenant_id, deck.id, len(pairs), is_new_deck=True)
    except Exception:
        logger.warning("notify_students_new_words (create) failed", exc_info=True)
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


class DeckFromVoiceRequest(BaseModel):
    audio_b64: str            # base64 без data-URL префіксу
    audio_mime: str = "audio/webm"


# MediaRecorder-mime → розширення для Whisper (той детектить формат по імені файлу).
_AUDIO_EXT = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/oga": "ogg",
    "audio/mp4": "mp4", "audio/x-m4a": "m4a", "audio/mp4a-latm": "mp4",
    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
}


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


@router.post("/api/teacher/decks/from_voice")
async def teacher_deck_from_voice(
    data: DeckFromVoiceRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Викладач диктує слова голосом → Whisper-транскрипт → пари «слово–переклад»
    (превʼю для редагування). Слова беруться мовою, яку викладає (target_lang),
    переклади підставляються автоматично. Колоду НЕ зберігає — повертає пари."""
    import base64
    from core.openai_client import transcribe_voice, extract_words_from_transcript
    from core.tenant_service import get_tenant_by_id, ai_snap_available, incr_ai_snap_usage

    teacher = await _require_teacher(telegram_id, tenant_id)
    if not _rl_allow(f"deckwrite:{tenant_id}:{telegram_id}", _DECK_WRITE_LIMIT, _DECK_WRITE_WINDOW):
        raise HTTPException(status_code=429, detail="rate_limited")

    tenant = await get_tenant_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    if not await ai_snap_available(tenant):
        raise HTTPException(status_code=429, detail="ai_snap_limit_reached")

    b64 = (data.audio_b64 or "").strip()
    if not b64:
        raise HTTPException(status_code=400, detail="no_audio")
    try:
        audio_bytes = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="bad_audio")

    ext = _AUDIO_EXT.get((data.audio_mime or "").split(";")[0].strip(), "webm")
    transcript, _lang = await transcribe_voice(audio_bytes, filename=f"voice.{ext}")
    target = teacher.target_lang or "en"
    native = teacher.native_lang or "uk"
    words = await extract_words_from_transcript(transcript, target_lang=target, native_lang=native)
    pairs_t = await ds.autofill_translations(
        [(w, None) for w in words], target_lang=target, native_lang=native,
    )
    pairs = [{"word": w, "translation": tr} for (w, tr) in pairs_t]

    await incr_ai_snap_usage(tenant_id)
    analytics.capture(telegram_id, "teacher_deck_voice_extracted", {
        "tenant_id": tenant_id, "pairs": len(pairs),
    })
    return {"ok": True, "pairs": pairs, "transcript": transcript}


@router.delete("/api/teacher/decks/{deck_id}")
async def teacher_delete_deck(
    deck_id: int, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Видаляє колоду разом із матеріалізованими словами учнів із неї."""
    await _require_teacher(telegram_id, tenant_id)
    ok = await ds.delete_deck(deck_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="deck_not_found")
    return {"ok": True}


@router.patch("/api/teacher/decks/{deck_id}")
async def teacher_update_deck(
    deck_id: int, data: DeckPatchRequest,
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    teacher = await _require_teacher(telegram_id, tenant_id)
    if not _rl_allow(f"deckwrite:{tenant_id}:{telegram_id}", _DECK_WRITE_LIMIT, _DECK_WRITE_WINDOW):
        raise HTTPException(status_code=429, detail="rate_limited")
    result: dict = {"ok": True}

    if data.add_text:
        entries = ds.parse_deck_entries(data.add_text)
        if entries:
            pairs = await ds.autofill_translations(
                entries,
                target_lang=(teacher.target_lang or "en"),
                native_lang=(teacher.native_lang or "uk"),
            )
            try:
                added = await ds.add_words_to_deck(deck_id, tenant_id, pairs)
            except ValueError:
                raise HTTPException(status_code=404, detail="deck_not_found")
            result["added_words"] = added
            if added:
                try:
                    await ds.notify_students_new_words(tenant_id, deck_id, added, is_new_deck=False)
                except Exception:
                    logger.warning("notify_students_new_words (add) failed", exc_info=True)

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


@router.get("/api/teacher/leaderboard")
async def teacher_leaderboard(
    telegram_id: int = Query(...), tenant_id: int = Query(1),
    group_id: int | None = Query(None),
):
    """M16: тижневий топ учнів (групи/тенанта) + готове повідомлення-привітання
    для пересилання в чат групи."""
    from core.leaderboard_service import group_leaderboard
    await _require_teacher(telegram_id, tenant_id)
    lb = await group_leaderboard(tenant_id, group_id)
    top3 = lb["rows"][:3]
    if top3:
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i]} {r['name']} — {r['reviews']} повторень" for i, r in enumerate(top3)]
        congrat = "🏆 <b>Топ тижня!</b>\n\n" + "\n".join(lines) + "\n\nВітаємо і тримаємо темп! 💪"
    else:
        congrat = None
    return {"top": lb["rows"], "top3": top3, "congrat_message": congrat,
            "week_start": lb["week_start"]}


# ─── Оплата сервісу викладачем ($19/міс) ─────────────────────────────────────

@router.get("/api/teacher/billing")
async def teacher_billing_status_endpoint(
    telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Статус підписки на сервіс для кабінету викладача (без rec_token)."""
    await _require_teacher(telegram_id, tenant_id)
    from core.tenant_service import tenant_billing_status
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return await tenant_billing_status(tenant)


class SeatsRequest(BaseModel):
    seats: int


@router.post("/api/teacher/billing/seats")
async def teacher_billing_set_seats(
    data: SeatsRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Власник обирає, за скільки викладачів платити (передоплата). Повертає
    оновлений статус підписки з новою ціною."""
    await _require_owner(telegram_id, tenant_id)
    from core.tenant_service import set_tenant_teacher_seats, tenant_billing_status
    tenant = await set_tenant_teacher_seats(tenant_id, data.seats)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return await tenant_billing_status(tenant)


@router.post("/api/teacher/billing/pay")
async def teacher_billing_pay(
    request: Request, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """URL на HPP-сторінку оплати сервісу ($19). Клієнт відкриває його через
    tg.openLink → /pay/tenant рендерить auto-submit форму WayForPay."""
    await _require_teacher(telegram_id, tenant_id)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if scheme == "http":
        scheme = "https"
    base = f"{scheme}://{request.url.netloc}"
    return {"payment_url": f"{base}/pay/tenant?tenant_id={tenant_id}"}


# ─── Інвайт-посилання школи ──────────────────────────────────────────────────

@router.get("/api/teacher/school/invites")
async def school_invites(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    """Посилання-запрошення: для owner — на викладачів + своє на учнів; для
    викладача — своє на учнів (кріпить учня до нього)."""
    teacher = await _require_teacher(telegram_id, tenant_id)
    from core.group_service import ensure_default_group, get_teacher_invite_token, is_school
    if not await is_school(tenant_id):
        return {"is_school": False}
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
    bot = (tenant.bot_username if tenant else None) or "WordSnapBot"
    out = {"is_school": True, "role": teacher.role}
    g = await ensure_default_group(tenant_id, teacher.id, teacher.first_name or "")
    out["student_invite_url"] = f"https://t.me/{bot}?start=s_{g.invite_token}"
    if teacher.role == "owner":
        token = await get_teacher_invite_token(tenant_id)
        out["teacher_invite_url"] = f"https://t.me/{bot}?start=t_{token}"
    return out


# ─── Школа: огляд по викладачах + призначення учнів (owner) ───────────────────

class AssignStudentRequest(BaseModel):
    student_user_id: int
    teacher_user_id: int


@router.get("/api/teacher/school/overview")
async def school_overview(telegram_id: int = Query(...), tenant_id: int = Query(1)):
    """Owner: по кожному викладачу — учнів, занять (всього/місяць/заплановано) +
    посилання-запрошення учнів до нього; плюс усі учні з поточним викладачем."""
    await _require_owner(telegram_id, tenant_id)
    from core import group_service as gs
    async with SessionLocal() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
    bot = (tenant.bot_username if tenant else None) or "WordSnapBot"
    # Гарантуємо дефолтні групи (щоб були invite-токени).
    for t in await gs.list_teachers(tenant_id):
        await gs.ensure_default_group(tenant_id, t["id"], t["name"])
    stats = await gs.school_teacher_stats(tenant_id)
    for t in stats:
        tok = t.pop("invite_token", None)
        t["invite_url"] = f"https://t.me/{bot}?start=s_{tok}" if tok else None
    return {"teachers": stats, "students": await gs.students_with_teacher(tenant_id)}


@router.post("/api/teacher/school/assign")
async def school_assign(
    data: AssignStudentRequest, telegram_id: int = Query(...), tenant_id: int = Query(1),
):
    """Owner призначає учня викладачу (переносить у дефолтну групу викладача)."""
    await _require_owner(telegram_id, tenant_id)
    from core.group_service import assign_student_to_teacher
    ok = await assign_student_to_teacher(tenant_id, data.student_user_id, data.teacher_user_id)
    if not ok:
        raise HTTPException(status_code=400, detail="assign_failed")
    return {"ok": True}
