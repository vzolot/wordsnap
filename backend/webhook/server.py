from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.db import engine
from webhook.api_routes import router as api_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    """Liveness/readiness — пінгує БД. Використовується UptimeRobot/Railway.

    HEAD підтримано, щоб UptimeRobot free tier (HEAD-only) працював.
    503 при недоступній БД, щоб алерт спрацював без keyword-моніторингу.
    """
    db_ok = False
    db_error = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)[:200]

    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "fail",
        "db_error": db_error,
    }
    return JSONResponse(payload, status_code=200 if db_ok else 503)
