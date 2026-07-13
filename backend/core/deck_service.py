"""Сервіс колод (white-label). Колода викладача = шаблон (`deck_words`), який
матеріалізується в персональні `words` учнів (зі своїм SRS-станом на кожного).

Інваріант видимості (учень бачить):
  • колоди СВОГО тенанта з assign_to_all = true, ПЛЮС
  • колоди свого тенанта, персонально призначені йому (deck_assignments).
Колоди інших тенантів і персональні колоди інших учнів — невидимі.

Матеріалізація ідемпотентна (ON CONFLICT DO NOTHING по (user_id, word,
target_lang)) — тому дописування слів у колоду НЕ скидає вже вивчене, а лише
додає нові рядки. Новий учень підхоплює assign_to_all-колоди при першому
sync (лениво, на завантаженні слів/ревʼю).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import Deck, DeckAssignment, DeckWord, User, Word


# ─── Парсинг «слово - переклад» / CSV ────────────────────────────────────────

# Роздільники у порядку пріоритету. Спершу таб (CSV-експорт), потім тире з
# пробілами (людський формат «слово - переклад»), потім ; та ,. «Голе» тире
# без пробілів — останнє, щоб не різати дефіси всередині слів.
def parse_word_pairs(text: str, limit: int = 500) -> list[tuple[str, str]]:
    """Толерантний парсер. Повертає список (word, translation), без дублів
    (за word.lower()), у порядку появи. Рядки, які не розбираються, пропускає."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        word = translation = None
        if "\t" in line:
            word, _, translation = line.partition("\t")
        else:
            m = re.search(r"\s+[-–—:]\s+", line)  # тире/двокрапка з пробілами
            if m:
                word = line[: m.start()]
                translation = line[m.end():]
            elif ";" in line:
                word, _, translation = line.partition(";")
            elif "," in line:
                word, _, translation = line.partition(",")
        if not word or not translation:
            continue
        word = word.strip()[:255]
        translation = translation.strip()[:500]
        if not word or not translation:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        pairs.append((word, translation))
        if len(pairs) >= limit:
            break
    return pairs


def parse_deck_entries(text: str, limit: int = 500) -> list[tuple[str, str | None]]:
    """Як parse_word_pairs, але переклад НЕОБОВʼЯЗКОВИЙ: рядок без роздільника
    (саме слово/фраза) → (word, None). None пізніше заповнить автопереклад."""
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        word = translation = None
        if "\t" in line:
            word, _, translation = line.partition("\t")
        else:
            m = re.search(r"\s+[-–—:]\s+", line)  # тире/двокрапка з пробілами
            if m:
                word = line[: m.start()]
                translation = line[m.end():]
            elif ";" in line:
                word, _, translation = line.partition(";")
            elif "," in line:
                word, _, translation = line.partition(",")
            else:
                word = line  # лише слово — переклад підставимо автоматично
        word = (word or "").strip()[:255]
        translation = ((translation or "").strip()[:500]) or None
        if not word:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((word, translation))
        if len(out) >= limit:
            break
    return out


async def autofill_translations(
    entries: list[tuple[str, str | None]], target_lang: str, native_lang: str,
) -> list[tuple[str, str]]:
    """Заповнює відсутні переклади через AI (get_word_data — та сама модель+кеш,
    що й у WordSnap). Якщо AI не дав переклад — лишаємо саме слово, щоб пара
    ніколи не була порожньою. Обмежена конкурентність (щоб не бити по rate-limit)."""
    from .openai_client import get_word_data

    sem = asyncio.Semaphore(5)

    async def resolve(word: str, tr: str | None) -> tuple[str, str]:
        if tr:
            return (word, tr)
        async with sem:
            try:
                data = await get_word_data(word, target_lang or "en", native_lang or "uk")
                t = ((data or {}).get("translation") or "").strip()
            except Exception:
                t = ""
        return (word, t or word)

    return list(await asyncio.gather(*[resolve(w, t) for (w, t) in entries]))


async def notify_students_new_words(
    tenant_id: int, deck_id: int, count: int, *, is_new_deck: bool,
) -> int:
    """Сповіщає учнів-адресатів колоди про нові слова (з бота тенанта). Викликати
    після create_deck/add_words_to_deck. Помилки надсилання ковтаються. Повертає
    к-сть надісланих."""
    if count <= 0:
        return 0
    async with SessionLocal() as session:
        deck = (await session.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            return 0
        user_ids = await _target_user_ids(session, deck)
        if not user_ids:
            return 0
        tg_ids = (await session.execute(
            select(User.telegram_id).where(
                User.id.in_(user_ids), User.role == "student",
            )
        )).scalars().all()
        title = deck.title

    if not tg_ids:
        return 0

    from html import escape
    from .telegram_send import send_message
    safe = escape(title or "колода")
    if is_new_deck:
        text = (f"📚 Ваш викладач додав нову колоду «{safe}» ({count} слів).\n"
                f"Відкрий додаток і почни вчити!")
    else:
        text = (f"✨ Ваш викладач додав {count} нових слів у колоду «{safe}».\n"
                f"Відкрий додаток, щоб їх повторити!")
    results = await asyncio.gather(
        *[send_message(tid, text, tenant_id=tenant_id) for tid in tg_ids],
        return_exceptions=True,
    )
    return sum(1 for r in results if not isinstance(r, Exception))


# ─── Видимість колод ─────────────────────────────────────────────────────────

def visible_decks_stmt(user_id: int, tenant_id: int):
    """SELECT видимих учню колод (для перевикористання/тестів)."""
    assigned = exists().where(
        and_(DeckAssignment.deck_id == Deck.id, DeckAssignment.user_id == user_id)
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
    async with SessionLocal() as session:
        rows = (await session.execute(
            visible_decks_stmt(user_id, tenant_id)
        )).scalars().all()
        return list(rows)


# ─── Матеріалізація колоди в words учнів ─────────────────────────────────────

async def _target_user_ids(session, deck: Deck) -> list[int]:
    """Учні, яким призначена ця колода: члени групи (group_id, school-режим),
    усі студенти тенанта (assign_to_all), або deck_assignments."""
    if deck.group_id:
        from .models import GroupMember
        rows = (await session.execute(
            select(GroupMember.user_id).where(GroupMember.group_id == deck.group_id)
        )).scalars().all()
    elif deck.assign_to_all:
        rows = (await session.execute(
            select(User.id).where(
                User.tenant_id == deck.tenant_id,
                User.role == "student",
            )
        )).scalars().all()
    else:
        rows = (await session.execute(
            select(DeckAssignment.user_id).where(DeckAssignment.deck_id == deck.id)
        )).scalars().all()
    return list(rows)


async def _materialize(session, deck: Deck, user_ids: list[int]) -> int:
    """Створює відсутні `words`-рядки з `deck_words` для заданих учнів.
    Ідемпотентно (ON CONFLICT (user_id, word, target_lang) DO NOTHING) — не
    чіпає вже наявні слова/прогрес. Повертає кількість вставлених рядків."""
    if not user_ids:
        return 0
    deck_words = (await session.execute(
        select(DeckWord).where(DeckWord.deck_id == deck.id)
    )).scalars().all()
    if not deck_words:
        return 0
    now = datetime.now(timezone.utc)
    inserted = 0
    for uid in user_ids:
        rows = [
            {
                "user_id": uid,
                "tenant_id": deck.tenant_id,
                "deck_id": deck.id,
                "word": dw.word.lower().strip(),
                "translation": dw.translation,
                "target_lang": (dw.target_lang or deck.target_lang or "en"),
                "next_review": now,  # доступне до повторення одразу
                "interval_days": 1.0,
                "ease_factor": 2.5,
                "review_count": 0,
                "status": "learning",
                "source": "deck",
            }
            for dw in deck_words
        ]
        stmt = pg_insert(Word).values(rows).on_conflict_do_nothing(
            index_elements=["user_id", "word", "target_lang"]
        )
        res = await session.execute(stmt)
        inserted += res.rowcount or 0
    return inserted


async def sync_decks_for_user(user_id: int, tenant_id: int) -> int:
    """Лениво матеріалізує в words усі видимі учню колоди. Викликати на
    завантаженні слів/ревʼю — новий учень так підхоплює assign_to_all-колоди,
    а вже призначені раніше — залишаються без змін (ідемпотентно)."""
    async with SessionLocal() as session:
        decks = (await session.execute(
            visible_decks_stmt(user_id, tenant_id)
        )).scalars().all()
        total = 0
        for deck in decks:
            total += await _materialize(session, deck, [user_id])
        if total:
            await session.commit()
        return total


# ─── CRUD викладача ──────────────────────────────────────────────────────────

async def create_deck(
    tenant_id: int,
    owner_user_id: int,
    title: str,
    pairs: list[tuple[str, str]],
    target_lang: str | None = None,
    assign_to_all: bool = True,
    assignee_user_ids: list[int] | None = None,
    group_id: int | None = None,
) -> Deck:
    """Створює колоду + deck_words + (за потреби) призначення, і матеріалізує
    слова адресатам. group_id (school) → членам групи; інакше assignee_user_ids
    коли assign_to_all=False. Адресати валідуються по тенанту."""
    # Груповий таргет вимикає assign_to_all.
    if group_id:
        assign_to_all = False
    async with SessionLocal() as session:
        deck = Deck(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            title=title.strip()[:200] or "Колода",
            target_lang=target_lang,
            assign_to_all=assign_to_all,
            group_id=group_id,
        )
        session.add(deck)
        await session.flush()  # отримати deck.id

        for pos, (w, tr) in enumerate(pairs):
            session.add(DeckWord(
                deck_id=deck.id, word=w, translation=tr,
                target_lang=target_lang, position=pos,
            ))

        if not assign_to_all and assignee_user_ids:
            valid_ids = (await session.execute(
                select(User.id).where(
                    User.id.in_(assignee_user_ids),
                    User.tenant_id == tenant_id,  # ізоляція: лише свої учні
                )
            )).scalars().all()
            for uid in valid_ids:
                session.add(DeckAssignment(deck_id=deck.id, user_id=uid))

        await session.flush()
        user_ids = await _target_user_ids(session, deck)
        await _materialize(session, deck, user_ids)
        await session.commit()
        await session.refresh(deck)
        return deck


async def add_words_to_deck(
    deck_id: int, tenant_id: int, pairs: list[tuple[str, str]]
) -> int:
    """Дописує слова в колоду і матеріалізує НОВІ слова адресатам (без скидання
    прогресу по старих). Повертає кількість доданих deck_words."""
    async with SessionLocal() as session:
        deck = (await session.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            raise ValueError("deck_not_found")
        existing = {
            w.lower() for w in (await session.execute(
                select(DeckWord.word).where(DeckWord.deck_id == deck.id)
            )).scalars().all()
        }
        base_pos = (await session.execute(
            select(func.coalesce(func.max(DeckWord.position), -1)).where(
                DeckWord.deck_id == deck.id
            )
        )).scalar() or -1
        added = 0
        for w, tr in pairs:
            if w.lower() in existing:
                continue
            base_pos += 1
            session.add(DeckWord(
                deck_id=deck.id, word=w, translation=tr,
                target_lang=deck.target_lang, position=base_pos,
            ))
            existing.add(w.lower())
            added += 1
        await session.flush()
        if added:
            user_ids = await _target_user_ids(session, deck)
            await _materialize(session, deck, user_ids)  # лише нові слова вставляться
        await session.commit()
        return added


async def remove_deck_word(deck_id: int, tenant_id: int, deck_word_id: int) -> bool:
    """Видаляє слово-шаблон з колоди. Уже матеріалізовані words учнів
    ЛИШАЮТЬСЯ (не чіпаємо їхній прогрес) — прибираємо лише з шаблону."""
    async with SessionLocal() as session:
        deck = (await session.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            return False
        res = await session.execute(
            delete(DeckWord).where(
                DeckWord.id == deck_word_id, DeckWord.deck_id == deck.id
            )
        )
        await session.commit()
        return (res.rowcount or 0) > 0


async def set_deck_assignees(
    deck_id: int, tenant_id: int, assignee_user_ids: list[int]
) -> int:
    """Перепризначає персональну колоду на заданий список учнів (додає нових,
    матеріалізує їм слова). Наявних не чіпає. Повертає кількість адресатів."""
    async with SessionLocal() as session:
        deck = (await session.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            raise ValueError("deck_not_found")
        valid_ids = set((await session.execute(
            select(User.id).where(
                User.id.in_(assignee_user_ids or []),
                User.tenant_id == tenant_id,
            )
        )).scalars().all())
        existing = set((await session.execute(
            select(DeckAssignment.user_id).where(DeckAssignment.deck_id == deck.id)
        )).scalars().all())
        for uid in valid_ids - existing:
            session.add(DeckAssignment(deck_id=deck.id, user_id=uid))
        await session.flush()
        newly = list(valid_ids - existing)
        if newly:
            await _materialize(session, deck, newly)
        await session.commit()
        return len(valid_ids)


async def list_teacher_decks(tenant_id: int, owner_user_id: int | None = None) -> list[dict]:
    """Колоди тенанта з кількістю слів і типом адресації — для дашборду викладача.
    owner_user_id (school-режим): якщо задано — лише колоди цього викладача."""
    async with SessionLocal() as session:
        q = select(Deck).where(Deck.tenant_id == tenant_id)
        if owner_user_id is not None:
            q = q.where(Deck.owner_user_id == owner_user_id)
        decks = (await session.execute(q.order_by(Deck.created_at.desc()))).scalars().all()
        out = []
        for d in decks:
            wc = (await session.execute(
                select(func.count(DeckWord.id)).where(DeckWord.deck_id == d.id)
            )).scalar() or 0
            if d.assign_to_all:
                addr = {"type": "all", "count": None}
            else:
                ac = (await session.execute(
                    select(func.count(DeckAssignment.id)).where(
                        DeckAssignment.deck_id == d.id
                    )
                )).scalar() or 0
                addr = {"type": "selected", "count": int(ac)}
            out.append({
                "id": d.id,
                "title": d.title,
                "target_lang": d.target_lang,
                "assign_to_all": d.assign_to_all,
                "word_count": int(wc),
                "assignment": addr,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })
        return out


async def get_deck_detail(deck_id: int, tenant_id: int) -> dict | None:
    """Колода зі словами і (для персональних) списком призначених user_id."""
    async with SessionLocal() as session:
        deck = (await session.execute(
            select(Deck).where(Deck.id == deck_id, Deck.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if deck is None:
            return None
        words = (await session.execute(
            select(DeckWord).where(DeckWord.deck_id == deck.id).order_by(DeckWord.position)
        )).scalars().all()
        assignees = (await session.execute(
            select(DeckAssignment.user_id).where(DeckAssignment.deck_id == deck.id)
        )).scalars().all()
        return {
            "id": deck.id,
            "title": deck.title,
            "target_lang": deck.target_lang,
            "assign_to_all": deck.assign_to_all,
            "words": [
                {"id": w.id, "word": w.word, "translation": w.translation}
                for w in words
            ],
            "assignee_user_ids": list(assignees),
        }


async def list_tenant_students(tenant_id: int) -> list[dict]:
    """Учні тенанта (role='student') — для пікера адресатів і дашборду."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.role == "student"
            ).order_by(User.created_at.asc())
        )).scalars().all()
        return [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "first_name": u.first_name,
                "username": u.username,
                # Імʼя для показу: first_name + @username (не лише username).
                "display_name": (
                    (u.first_name or "").strip()
                    + (f" @{u.username}" if u.username else "")
                ).strip() or (f"@{u.username}" if u.username else f"id{u.telegram_id}"),
            }
            for u in rows
        ]
