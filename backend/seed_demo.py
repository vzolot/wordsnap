"""Наповнення ДЕМО-тенантів (t2 Марта, t3 Мовна школа) прикладовим контентом:
студенти з прогресом, викладачі (для школи), колоди зі словами, повторення для
статистики. Ідемпотентно: спершу чистить попередній демо-контент. НІКОЛИ не чіпає
WordSnap (t1). Запуск:  cd backend && railway run python seed_demo.py
"""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from core.db import SessionLocal
from core.models import User, Word, Review, Deck, DeckWord, Group, GroupMember

NOW = datetime.now(timezone.utc)
OWNER_TG = 469478065  # Vova — owner обох демо-тенантів

PL = [("dzień dobry", "добрий день"), ("dziękuję", "дякую"), ("proszę", "будь ласка"),
      ("woda", "вода"), ("chleb", "хліб"), ("dom", "дім"), ("kot", "кіт"),
      ("książka", "книга"), ("okno", "вікно"), ("stół", "стіл")]
EN = [("hello", "привіт"), ("water", "вода"), ("bread", "хліб"), ("house", "дім"),
      ("book", "книга"), ("window", "вікно"), ("table", "стіл"), ("fast", "швидко"),
      ("remember", "пам’ятати"), ("learn", "вчити")]
DE = [("Hallo", "привіт"), ("Wasser", "вода"), ("Brot", "хліб"), ("Haus", "дім"),
      ("Buch", "книга"), ("Fenster", "вікно"), ("Tisch", "стіл"), ("schnell", "швидко")]


async def owner_uid(s, tenant_id):
    u = (await s.execute(select(User).where(User.tenant_id == tenant_id, User.telegram_id == OWNER_TG))).scalar_one_or_none()
    return u.id if u else None


async def make_deck(s, tenant_id, owner, title, pairs, tlang, group_id=None):
    d = Deck(tenant_id=tenant_id, owner_user_id=owner, title=title, target_lang=tlang,
             assign_to_all=(group_id is None), group_id=group_id)
    s.add(d); await s.flush()
    for i, (w, tr) in enumerate(pairs):
        s.add(DeckWord(deck_id=d.id, word=w, translation=tr, target_lang=tlang, position=i))
    return d.id, pairs, tlang


async def make_student(s, tenant_id, tg, name, tlang, xp, streak, decks):
    u = User(telegram_id=tg, tenant_id=tenant_id, role="student", first_name=name,
             native_lang="uk", target_lang=tlang, total_xp=xp, streak_days=streak,
             last_active_at=NOW - timedelta(hours=3))
    s.add(u); await s.flush()
    review_word_ids = []
    for deck_id, pairs, tl in decks:
        for i, (w, tr) in enumerate(pairs):
            mastered = i < (len(pairs) * 3) // 5   # ~60% вивчено
            word = Word(user_id=u.id, tenant_id=tenant_id, deck_id=deck_id, word=w, translation=tr,
                        target_lang=tl, next_review=NOW + timedelta(days=1),
                        status=("mastered" if mastered else "learning"),
                        review_count=(5 if mastered else 1), correct_count=(5 if mastered else 1),
                        source="deck", last_reviewed_at=NOW - timedelta(hours=5))
            s.add(word); await s.flush()
            if len(review_word_ids) < 3:
                review_word_ids.append(word.id)
    # повторення за останні дні → стрік + активність 7д
    days = min(max(streak, 1), 6)
    for d in range(days):
        for wid in review_word_ids:
            s.add(Review(word_id=wid, user_id=u.id, tenant_id=tenant_id, result="knew",
                         reviewed_at=NOW - timedelta(days=d, hours=1)))
    return u.id


async def make_teacher(s, tenant_id, tg, name):
    u = User(telegram_id=tg, tenant_id=tenant_id, role="teacher", first_name=name,
             native_lang="uk", target_lang="en", is_active_teacher=True,
             last_active_at=NOW - timedelta(hours=4))
    s.add(u); await s.flush()
    g = Group(tenant_id=tenant_id, name=f"Група — {name}", teacher_user_id=u.id, is_default=True)
    s.add(g); await s.flush()
    return u.id, g.id


async def cleanup(s):
    await s.execute(delete(Deck).where(Deck.title.like("Демо:%"), Deck.tenant_id.in_([2, 3])))
    await s.execute(delete(User).where(User.telegram_id >= 9_100_000_000, User.tenant_id.in_([2, 3])))
    await s.execute(delete(Group).where(Group.name.like("Група — %"), Group.tenant_id == 3))
    await s.commit()


async def main():
    async with SessionLocal() as s:
        await cleanup(s)

        # ── Марта (t2, соло-репетитор, польська) ──────────────────────────────
        o2 = await owner_uid(s, 2)
        d1 = await make_deck(s, 2, o2, "Демо: Побут A1", PL[:5], "pl")
        d2 = await make_deck(s, 2, o2, "Демо: Їжа і дім", PL[5:], "pl")
        marta_students = [
            ("Олена", 980, 21), ("Іван", 420, 7), ("Катерина", 1540, 33),
            ("Марко", 260, 4), ("Софія", 730, 12),
        ]
        for i, (name, xp, st) in enumerate(marta_students):
            await make_student(s, 2, 9_100_000_001 + i, name, "pl", xp, st, [d1, d2])

        # ── Мовна школа (t3, кілька викладачів) ───────────────────────────────
        o3 = await owner_uid(s, 3)
        t1_id, g1 = await make_teacher(s, 3, 9_200_000_001, "Анна")
        t2_id, g2 = await make_teacher(s, 3, 9_200_000_002, "Петро")
        de_deck = await make_deck(s, 3, t1_id, "Демо: English Starter", EN[:6], "en", group_id=g1)
        de_deck2 = await make_deck(s, 3, t2_id, "Демо: Deutsch A1", DE, "de", group_id=g2)
        # студенти Анни (англ)
        anna_students = [("Дарина", 640, 9), ("Богдан", 1120, 18), ("Юлія", 300, 5)]
        for i, (name, xp, st) in enumerate(anna_students):
            uid = await make_student(s, 3, 9_200_000_011 + i, name, "en", xp, st, [de_deck])
            s.add(GroupMember(group_id=g1, user_id=uid))
        # студенти Петра (нім)
        petro_students = [("Максим", 880, 14), ("Аліна", 210, 3)]
        for i, (name, xp, st) in enumerate(petro_students):
            uid = await make_student(s, 3, 9_200_000_021 + i, name, "de", xp, st, [de_deck2])
            s.add(GroupMember(group_id=g2, user_id=uid))

        await s.commit()

    # звіт
    async with SessionLocal() as s:
        for tid in (2, 3):
            n_stu = (await s.execute(select(User).where(User.tenant_id == tid, User.role == "student", User.telegram_id >= 9_100_000_000))).scalars().all()
            n_tea = (await s.execute(select(User).where(User.tenant_id == tid, User.role == "teacher", User.telegram_id >= 9_100_000_000))).scalars().all()
            n_deck = (await s.execute(select(Deck).where(Deck.tenant_id == tid, Deck.title.like("Демо:%")))).scalars().all()
            print(f"tenant {tid}: students={len(n_stu)} teachers={len(n_tea)} decks={len(n_deck)}")


asyncio.run(main())
