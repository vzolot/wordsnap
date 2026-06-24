import logging
import os
from urllib.parse import urlencode, parse_qs

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from core.db import engine
from core.tg_auth import verify_init_data
from webhook.api_routes import router as api_router

logger = logging.getLogger(__name__)

app = FastAPI()

# /api/* шляхи, які лишаються публічними (без initData-автентифікації):
#   - WayForPay server-to-server callback (перевіряється власним підписом);
#   - lead-capture з анонімного лендера (без Telegram-контексту).
# Усе інше під /api/* вимагає валідний X-Telegram-Init-Data. Шляхи поза /api/
# (/pay, /wayforpay/callback, /health) природно не гейтяться.
_PUBLIC_API_PATHS = {"/api/wayforpay/callback", "/api/lead/capture"}
# Аварійний вимикач: REQUIRE_TG_AUTH=0 у Railway env миттєво вимикає
# enforcement (лише логування), якщо щось масово ламається на проді.
_REQUIRE_TG_AUTH = os.getenv("REQUIRE_TG_AUTH", "1") == "1"


@app.middleware("http")
async def telegram_auth_middleware(request: Request, call_next):
    """Гейтить /api/* за валідним initData. Перевірений telegram_id
    підставляється у query-параметр (override клієнтського значення), тож
    ендпойнти лишають `telegram_id: int = Query(...)` без змін, але значення
    тепер довірене — підробити заголовок без токена бота неможливо."""
    path = request.url.path
    if (
        request.method != "OPTIONS"
        and path.startswith("/api/")
        and path not in _PUBLIC_API_PATHS
    ):
        tg_id = verify_init_data(request.headers.get("x-telegram-init-data", ""))
        if tg_id is None:
            if _REQUIRE_TG_AUTH:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            logger.warning("tg-auth: missing/invalid initData for %s (enforcement OFF)", path)
        else:
            # Перезаписуємо telegram_id перевіреним значенням.
            params = parse_qs(request.scope.get("query_string", b"").decode())
            params["telegram_id"] = [str(tg_id)]
            request.scope["query_string"] = urlencode(params, doseq=True).encode()
    return await call_next(request)


# CORS додаємо ПІСЛЯ auth-middleware → він стає зовнішнім, тому навіть 401
# від auth отримує CORS-заголовки. allow_origins="*" безпечно: запити тепер
# вимагають підписаний X-Telegram-Init-Data, який чужий origin не підробить.
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
