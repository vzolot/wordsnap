from fastapi import APIRouter, Query
from core.db import get_db

router = APIRouter()

@router.get("/api/words")
async def get_words(telegram_id: int = Query(...)):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, word, translation, example, repetition FROM words WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) ORDER BY created_at DESC",
            (telegram_id,)
        )
        words = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, w)) for w in words]

@router.get("/api/stats")
async def get_stats(telegram_id: int = Query(...)):
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        user = await cursor.fetchone()
        if not user:
            return {"total_words": 0, "learned_words": 0, "reviewed_today": 0, "streak": 0}
        uid = user[0]
        cursor = await db.execute("SELECT COUNT(*) FROM words WHERE user_id = ?", (uid,))
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM words WHERE user_id = ? AND repetition >= 3", (uid,))
        learned = (await cursor.fetchone())[0]
        return {"total_words": total, "learned_words": learned, "reviewed_today": 0, "streak": 0}

@router.get("/api/review")
async def get_review_words(telegram_id: int = Query(...)):
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, word, translation, example FROM words WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) AND (next_review IS NULL OR next_review <= ?)",
            (telegram_id, now)
        )
        words = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, w)) for w in words]

@router.post("/api/review")
async def submit_review(data: dict, telegram_id: int = Query(...)):
    from datetime import datetime, timedelta
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM words WHERE id = ?", (data["word_id"],))
        word = await cursor.fetchone()
        if word:
            next_review = (datetime.utcnow() + timedelta(days=data.get("quality", 3))).isoformat()
            rep = (word[6] or 0) + 1
            await db.execute(
                "UPDATE words SET next_review = ?, repetition = ? WHERE id = ?",
                (next_review, rep, data["word_id"])
            )
            await db.commit()
        return {"ok": True}
