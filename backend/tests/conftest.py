"""Спільні хелпери для DB-тестів.

Проблема: сервіси роблять `from .db import SessionLocal` на імпорті, тож
переприсвоєння `core.db.SessionLocal` у тесті НЕ оновлює вже імпортовані модулі.
Плюс pytest-asyncio дає кожному тесту свій event loop. Разом це давало
«attached to a different loop» коли ≥2 DB-тести ділили stale engine.

`bind_test_engine(SessionLocal)` явно проставляє SessionLocal у core.db І в усі
сервіс-модулі, що його закешували — тож кожен тест користується СВОЇМ engine
на СВОЄМУ loop. Викликати ПІСЛЯ імпорту потрібних сервісів у тесті."""
import sys

_SERVICE_MODULES = [
    "core.user_service", "core.word_service", "core.deck_service",
    "core.calendar_service", "core.teacher_stats", "core.tenant_service",
]


def bind_test_engine(session_local) -> None:
    import core.db as core_db
    core_db.SessionLocal = session_local
    for name in _SERVICE_MODULES:
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "SessionLocal"):
            mod.SessionLocal = session_local
