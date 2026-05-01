from fastapi import APIRouter, Query
from core.db import get_db_connection

router = APIRouter()

@router.get("/api/words")
async def get_words(telegram_id: int = Query(...)):
    conn = get_db_connection()
    try:
        words = conn.execute(
            "SELECT id, word, translation, example, repetition FROM words WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) ORDER BY created_at DESC",
            (telegram_id,)
        ).fetchall()
        return [dict(w) for w in words]
    finally:
        conn.close()

@router.get("/api/stats")
async def get_stats(telegram_id: int = Query(...)):
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not user:
            return {"total_words": 0, "learned_words": 0, "reviewed_today": 0, "streak": 0}
        uid = user["id"]
        total = conn.execute("SELECT COUNT(*) FROM words WHERE user_id = ?", (uid,)).fetchone()[0]
        learned = conn.execute("SELECT COUNT(*) FROM words WHERE user_id = ? AND repetition >= 3", (uid,)).fetchone()[0]
        return {"total_words": total, "learned_words": learned, "reviewed_today": 0, "streak": 0}
    finally:
        conn.close()

@router.get("/api/review")
async def get_review_words(telegram_id: int = Query(...)):
    from datetime import datetime
    conn = get_db_connection()
    try:
        now = datetime.utcnow().isoformat()
        words = conn.execute(
            "SELECT id, word, translation, example FROM words WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) AND (next_review IS NULL OR next_review <= ?)",
            (telegram_id, now)
        ).fetchall()
        return [dict(w) for w in words]
    finally:
        conn.close()

@router.post("/api/review")
async def submit_review(data: dict, telegram_id: int = Query(...)):
    from core.srs import calculate_next_review
    from datetime import datetime
    conn = get_db_connection()
    try:
        word = conn.execute("SELECT * FROM words WHERE id = ?", (data["word_id"],)).fetchone()
        if word:
            next_review, new_rep = calculate_next_review(dict(word), data["quality"])
            conn.execute(
                "UPDATE words SET next_review = ?, repetition = ? WHERE id = ?",
                (next_review, new_rep, data["word_id"])
            )
            conn.commit()
        return {"ok": True}
    finally:
        conn.close()
