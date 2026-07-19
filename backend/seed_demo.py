"""Наповнення ДЕМО-тенантів (t2 Марта, t3 Мовна школа) прикладовим контентом:
студенти з прогресом, викладачі, колоди (слова + фрази), доступність (календар),
уроки (для статистики). Ідемпотентно. НІКОЛИ не чіпає WordSnap (t1).
Запуск:  cd backend && railway run .venv/bin/python seed_demo.py
"""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from core.db import SessionLocal
from core.models import (User, Word, Review, Deck, DeckWord, Group, GroupMember,
                         Lesson, TeacherAvailability)

NOW = datetime.now(timezone.utc)
MONTH_START = NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
OWNER_TG = 469478065

# Колоди: слова + фрази (щоб було видно не лише окремі слова)
PL_A = [("dzień dobry", "добрий день"), ("dziękuję", "дякую"), ("proszę", "будь ласка"),
        ("woda", "вода"), ("chleb", "хліб"), ("jak się masz?", "як справи?")]
PL_B = [("dom", "дім"), ("książka", "книга"), ("okno", "вікно"), ("stół", "стіл"),
        ("do zobaczenia", "до побачення"), ("miło mi", "дуже приємно")]
EN_A = [("hello", "привіт"), ("water", "вода"), ("book", "книга"), ("window", "вікно"),
        ("how are you?", "як справи?"), ("see you soon", "до зустрічі")]
DE_A = [("Hallo", "привіт"), ("Wasser", "вода"), ("Buch", "книга"), ("Tisch", "стіл"),
        ("wie geht's?", "як справи?"), ("bis bald", "до зустрічі")]


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
    rev_ids = []
    for deck_id, pairs, tl in decks:
        for i, (w, tr) in enumerate(pairs):
            mastered = i < (len(pairs) * 3) // 5
            word = Word(user_id=u.id, tenant_id=tenant_id, deck_id=deck_id, word=w, translation=tr,
                        target_lang=tl, next_review=NOW + timedelta(days=1),
                        status=("mastered" if mastered else "learning"),
                        review_count=(5 if mastered else 1), correct_count=(5 if mastered else 1),
                        source="deck", last_reviewed_at=NOW - timedelta(hours=5))
            s.add(word); await s.flush()
            if len(rev_ids) < 3:
                rev_ids.append(word.id)
    for d in range(min(max(streak, 1), 6)):
        for wid in rev_ids:
            s.add(Review(word_id=wid, user_id=u.id, tenant_id=tenant_id, result="knew",
                         reviewed_at=NOW - timedelta(days=d, hours=1)))
    return u.id


async def make_teacher(s, tenant_id, tg, name, tlang):
    u = User(telegram_id=tg, tenant_id=tenant_id, role="teacher", first_name=name,
             native_lang="uk", target_lang=tlang, is_active_teacher=True,
             last_active_at=NOW - timedelta(hours=4))
    s.add(u); await s.flush()
    g = Group(tenant_id=tenant_id, name=f"Група — {name}", teacher_user_id=u.id, is_default=True)
    s.add(g); await s.flush()
    return u.id, g.id


def availability(s, tenant_id, teacher_uid):
    # Пн/Ср/Пт: 10:00–13:00 та 15:00–19:00
    for wd in (0, 2, 4):
        s.add(TeacherAvailability(tenant_id=tenant_id, teacher_user_id=teacher_uid, weekday=wd, start_min=600, end_min=780))
        s.add(TeacherAvailability(tenant_id=tenant_id, teacher_user_id=teacher_uid, weekday=wd, start_min=900, end_min=1140))


def lessons(s, tenant_id, teacher_uid, student_uids):
    # унікальний час у викладача (constraint uq_lessons_teacher_slot):
    # проведені цього місяця (days≈2 тому) + заплановані наперед.
    slot = 0
    for su in student_uids:
        for _ in range(3):
            when = NOW - timedelta(days=2, minutes=slot * 53)
            s.add(Lesson(tenant_id=tenant_id, teacher_user_id=teacher_uid, student_user_id=su,
                         starts_at_utc=when, duration_min=60, status="completed"))
            slot += 1
        for _ in range(2):
            when = NOW + timedelta(days=1, minutes=slot * 53)
            s.add(Lesson(tenant_id=tenant_id, teacher_user_id=teacher_uid, student_user_id=su,
                         starts_at_utc=when, duration_min=60, status="booked"))
            slot += 1


async def cleanup(s):
    await s.execute(delete(Lesson).where(Lesson.tenant_id.in_([2, 3])))
    await s.execute(delete(TeacherAvailability).where(TeacherAvailability.tenant_id.in_([2, 3])))
    await s.execute(delete(Deck).where(Deck.title.like("Демо:%"), Deck.tenant_id.in_([2, 3])))
    await s.execute(delete(User).where(User.telegram_id >= 9_100_000_000, User.tenant_id.in_([2, 3])))
    await s.execute(delete(Group).where(Group.name.like("Група — %"), Group.tenant_id == 3))
    await s.commit()


async def main():
    async with SessionLocal() as s:
        await cleanup(s)

        # ── Марта (t2, соло-репетитор, польська) ──────────────────────────────
        o2 = await owner_uid(s, 2)
        d1 = await make_deck(s, 2, o2, "Демо: Побут A1", PL_A, "pl")
        d2 = await make_deck(s, 2, o2, "Демо: Фрази і дім", PL_B, "pl")
        marta_students = [("Олена", 980, 21), ("Іван", 420, 7), ("Катерина", 1540, 33),
                          ("Марко", 260, 4), ("Софія", 730, 12)]
        m_uids = []
        for i, (name, xp, st) in enumerate(marta_students):
            m_uids.append(await make_student(s, 2, 9_100_000_001 + i, name, "pl", xp, st, [d1, d2]))
        availability(s, 2, o2)
        lessons(s, 2, o2, m_uids)

        # ── Мовна школа (t3) ──────────────────────────────────────────────────
        o3 = await owner_uid(s, 3)
        anna_id, ga = await make_teacher(s, 3, 9_200_000_001, "Анна", "en")
        petro_id, gp = await make_teacher(s, 3, 9_200_000_002, "Петро", "de")
        en_deck = await make_deck(s, 3, anna_id, "Демо: English Starter", EN_A, "en", group_id=ga)
        de_deck = await make_deck(s, 3, petro_id, "Демо: Deutsch A1", DE_A, "de", group_id=gp)
        anna_students = [("Дарина", 640, 9), ("Богдан", 1120, 18), ("Юлія", 300, 5)]
        a_uids = []
        for i, (name, xp, st) in enumerate(anna_students):
            uid = await make_student(s, 3, 9_200_000_011 + i, name, "en", xp, st, [en_deck])
            s.add(GroupMember(group_id=ga, user_id=uid)); a_uids.append(uid)
        petro_students = [("Максим", 880, 14), ("Аліна", 210, 3)]
        p_uids = []
        for i, (name, xp, st) in enumerate(petro_students):
            uid = await make_student(s, 3, 9_200_000_021 + i, name, "de", xp, st, [de_deck])
            s.add(GroupMember(group_id=gp, user_id=uid)); p_uids.append(uid)
        availability(s, 3, anna_id); lessons(s, 3, anna_id, a_uids)
        availability(s, 3, petro_id); lessons(s, 3, petro_id, p_uids)

        # ── Група власника (Volodymyr) у школі — щоб «Як викладач» не був порожній
        vg = (await s.execute(select(Group).where(Group.tenant_id == 3, Group.teacher_user_id == o3))).scalars().first()
        if vg is None:
            vg = Group(tenant_id=3, name="Група — Volodymyr", teacher_user_id=o3, is_default=True)
            s.add(vg); await s.flush()
        v_deck = await make_deck(s, 3, o3, "Демо: English A2", EN_A, "en", group_id=vg.id)
        vova_students = [("Наталя", 560, 8), ("Олексій", 990, 16)]
        v_uids = []
        for i, (name, xp, st) in enumerate(vova_students):
            uid = await make_student(s, 3, 9_200_000_031 + i, name, "en", xp, st, [v_deck])
            s.add(GroupMember(group_id=vg.id, user_id=uid)); v_uids.append(uid)
        availability(s, 3, o3); lessons(s, 3, o3, v_uids)

        await s.commit()

    async with SessionLocal() as s:
        for tid in (2, 3):
            stu = len((await s.execute(select(User).where(User.tenant_id == tid, User.role == "student", User.telegram_id >= 9_100_000_000))).scalars().all())
            tea = len((await s.execute(select(User).where(User.tenant_id == tid, User.role == "teacher", User.telegram_id >= 9_100_000_000))).scalars().all())
            les = len((await s.execute(select(Lesson).where(Lesson.tenant_id == tid))).scalars().all())
            av = len((await s.execute(select(TeacherAvailability).where(TeacherAvailability.tenant_id == tid))).scalars().all())
            print(f"tenant {tid}: students={stu} teachers={tea} lessons={les} availability_slots={av}")


asyncio.run(main())
