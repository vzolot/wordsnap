"""Агрегати для дашборду викладача (white-label M6).

Усе рахується bulk-запитами (без N+1) і строго в межах тенанта. Дати streak/
активності — за UTC (достатньо для оглядового дашборду; персональні TZ учня
використовує реальний scheduler)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import SessionLocal
from .models import Deck, User, Word, Review

# Скільки днів бездіяльності → бейдж «в ризику».
RISK_INACTIVE_DAYS = 5
WEAK_MIN_REVIEWS = 3  # мінімум повторень слова, щоб рахувати частку помилок
WEAK_TOP_N = 10


async def weak_word_ids(user_id: int, limit: int = WEAK_TOP_N, min_reviews: int = WEAK_MIN_REVIEWS) -> list[int]:
    """ID слів учня з найбільшою часткою помилок (forgot+struggled)/total,
    з мінімум min_reviews повторень. Спільна логіка для дашборду, дайджесту
    (M10) і кнопки «повторити слабкі» учню."""
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(Review.word_id, Review.result, func.count(Review.id)).where(
                Review.user_id == user_id,
            ).group_by(Review.word_id, Review.result)
        )).all()
    agg: dict[int, dict] = {}
    for wid, res, n in rows:
        a = agg.setdefault(wid, {"total": 0, "err": 0})
        a["total"] += int(n)
        if res in ("forgot", "struggled"):
            a["err"] += int(n)
    ranked = [
        (wid, a["err"] / a["total"], a["total"])
        for wid, a in agg.items()
        if a["total"] >= min_reviews and a["err"] > 0
    ]
    ranked.sort(key=lambda t: (t[1], t[2]), reverse=True)
    return [wid for wid, _, _ in ranked[:limit]]


def _streak_from_dates(dates: list) -> int:
    """dates — унікальні дати повторень за спаданням. Логіка як у streaks.py."""
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if dates[0] != today and dates[0] != yesterday:
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if dates[i] == dates[i - 1] - timedelta(days=1):
            streak += 1
        else:
            break
    return streak


async def students_overview(tenant_id: int) -> list[dict]:
    """Список учнів тенанта з агрегатами: стрік, повторень за 7д, останній
    візит, % вивчених слів з колод викладача, прапор ризику. Сортування:
    неактивні зверху (кому варто написати)."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    async with SessionLocal() as s:
        students = (await s.execute(
            select(User).where(User.tenant_id == tenant_id, User.role == "student")
        )).scalars().all()
        if not students:
            return []
        ids = [u.id for u in students]

        # повторень за 7 днів (bulk)
        rows7 = (await s.execute(
            select(Review.user_id, func.count(Review.id)).where(
                Review.tenant_id == tenant_id,
                Review.user_id.in_(ids),
                Review.reviewed_at >= week_ago,
            ).group_by(Review.user_id)
        )).all()
        reviews_7d = {uid: int(n) for uid, n in rows7}

        # останній візит = MAX(reviewed_at) (bulk)
        rows_last = (await s.execute(
            select(Review.user_id, func.max(Review.reviewed_at)).where(
                Review.tenant_id == tenant_id, Review.user_id.in_(ids),
            ).group_by(Review.user_id)
        )).all()
        last_review = {uid: ts for uid, ts in rows_last}

        # унікальні дати повторень для стріку (bulk, одним запитом на всіх)
        rows_days = (await s.execute(
            select(Review.user_id, func.date(Review.reviewed_at)).where(
                Review.tenant_id == tenant_id, Review.user_id.in_(ids),
            ).distinct()
        )).all()
        days_by_user: dict[int, list] = {}
        for uid, d in rows_days:
            days_by_user.setdefault(uid, []).append(d)

        # прогрес по колодах викладача: total і mastered (bulk)
        rows_deck = (await s.execute(
            select(
                Word.user_id,
                func.count(Word.id),
                func.count(Word.id).filter(Word.status == "mastered"),
            ).where(
                Word.tenant_id == tenant_id,
                Word.user_id.in_(ids),
                Word.deck_id.isnot(None),
            ).group_by(Word.user_id)
        )).all()
        deck_progress = {uid: (int(total), int(mastered)) for uid, total, mastered in rows_deck}

    out = []
    for u in students:
        total, mastered = deck_progress.get(u.id, (0, 0))
        pct = round(100 * mastered / total) if total else 0
        last = last_review.get(u.id)
        days_since = (now - last).days if last else None
        dates = sorted(days_by_user.get(u.id, []), reverse=True)
        at_risk = last is None or (days_since is not None and days_since >= RISK_INACTIVE_DAYS)
        out.append({
            "id": u.id,
            "telegram_id": u.telegram_id,
            "first_name": u.first_name,
            "username": u.username,
            "display_name": (
                (u.first_name or "").strip() + (f" @{u.username}" if u.username else "")
            ).strip() or (f"@{u.username}" if u.username else f"id{u.telegram_id}"),
            "streak": _streak_from_dates(dates),
            "reviews_7d": reviews_7d.get(u.id, 0),
            "last_visit": last.isoformat() if last else None,
            "days_since_visit": days_since,
            "deck_words_total": total,
            "deck_words_learned": mastered,
            "learned_pct": pct,
            "at_risk": at_risk,
        })

    # неактивні зверху: None (ніколи) першими, далі за найдавнішим візитом.
    out.sort(key=lambda r: (r["last_visit"] is not None, r["last_visit"] or ""))
    return out


async def student_detail(tenant_id: int, user_id: int) -> dict | None:
    """Детальний прогрес одного учня: стрік, активність 7/30д, прогрес по
    кожній призначеній колоді, топ-10 слабких слів (за часткою помилок)."""
    now = datetime.now(timezone.utc)
    d30 = now - timedelta(days=30)
    d7 = now - timedelta(days=7)

    async with SessionLocal() as s:
        user = (await s.execute(
            select(User).where(
                User.id == user_id, User.tenant_id == tenant_id, User.role == "student",
            )
        )).scalar_one_or_none()
        if user is None:
            return None

        # активність по днях за 30 днів
        rows_act = (await s.execute(
            select(func.date(Review.reviewed_at), func.count(Review.id)).where(
                Review.user_id == user_id, Review.reviewed_at >= d30,
            ).group_by(func.date(Review.reviewed_at))
        )).all()
        activity = {str(d): int(n) for d, n in rows_act}
        reviews_30d = sum(activity.values())
        reviews_7d = (await s.execute(
            select(func.count(Review.id)).where(
                Review.user_id == user_id, Review.reviewed_at >= d7,
            )
        )).scalar() or 0

        # стрік
        all_days = sorted([r[0] for r in (await s.execute(
            select(func.date(Review.reviewed_at)).where(
                Review.user_id == user_id
            ).distinct()
        )).all()], reverse=True)
        streak = _streak_from_dates(all_days)

        # прогрес по кожній призначеній колоді (за словами учня з deck_id)
        rows_deck = (await s.execute(
            select(
                Word.deck_id, Deck.title, Word.status, Word.review_count, func.count(Word.id),
            ).join(Deck, Deck.id == Word.deck_id).where(
                Word.user_id == user_id, Word.deck_id.isnot(None),
            ).group_by(Word.deck_id, Deck.title, Word.status, Word.review_count)
        )).all()
        decks: dict[int, dict] = {}
        for deck_id, title, status, rc, n in rows_deck:
            d = decks.setdefault(deck_id, {
                "deck_id": deck_id, "title": title,
                "learned": 0, "in_progress": 0, "not_started": 0,
            })
            n = int(n)
            if status == "mastered":
                d["learned"] += n
            elif (rc or 0) > 0:
                d["in_progress"] += n
            else:
                d["not_started"] += n

        # слабкі слова: частка помилок (forgot+struggled)/total, min N повторень
        rows_res = (await s.execute(
            select(Review.word_id, Review.result, func.count(Review.id)).where(
                Review.user_id == user_id,
            ).group_by(Review.word_id, Review.result)
        )).all()
        agg: dict[int, dict] = {}
        for wid, res, n in rows_res:
            a = agg.setdefault(wid, {"total": 0, "err": 0})
            a["total"] += int(n)
            if res in ("forgot", "struggled"):
                a["err"] += int(n)
        weak_ids = [
            (wid, a["err"] / a["total"], a["total"])
            for wid, a in agg.items()
            if a["total"] >= WEAK_MIN_REVIEWS and a["err"] > 0
        ]
        weak_ids.sort(key=lambda t: (t[1], t[2]), reverse=True)
        weak_ids = weak_ids[:WEAK_TOP_N]
        weak = []
        if weak_ids:
            wmap = {
                w.id: w for w in (await s.execute(
                    select(Word).where(Word.id.in_([w for w, _, _ in weak_ids]))
                )).scalars().all()
            }
            for wid, rate, total in weak_ids:
                w = wmap.get(wid)
                if w:
                    weak.append({
                        "word_id": wid, "word": w.word, "translation": w.translation,
                        "error_rate": round(rate, 2), "reviews": total,
                    })

    return {
        "id": user.id,
        "display_name": (
            (user.first_name or "").strip() + (f" @{user.username}" if user.username else "")
        ).strip() or f"id{user.telegram_id}",
        "streak": streak,
        "reviews_7d": int(reviews_7d),
        "reviews_30d": reviews_30d,
        "activity": activity,               # {'YYYY-MM-DD': count}
        "decks": list(decks.values()),
        "weak_words": weak,
    }
