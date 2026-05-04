"""
Sentry initialization. Викликати ОДИН раз на старті процесу,
ДО створення FastAPI app та aiogram bot.

Set SENTRY_DSN env var щоб увімкнути. Без DSN — no-op.
"""
import logging
import os

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN not set — skipping Sentry init")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        environment = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENV") or "production"
        release = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("RELEASE")

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=0.1,   # 10% запитів — для performance metrics
            profiles_sample_rate=0.0, # вимкнено для економії
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
            ],
            send_default_pii=False,
            before_send=_filter_event,
        )
        logger.info(f"Sentry initialized (env={environment})")
    except Exception as e:
        logger.warning(f"Sentry init failed: {e}")


def _filter_event(event, hint):
    """Прибираємо шум — handled exceptions, які не потребують tracking."""
    # Telegram «message is not modified» — нормально для edit_text
    exc = hint.get("exc_info")
    if exc:
        msg = str(exc[1])
        if "message is not modified" in msg:
            return None
        if "MESSAGE_NOT_MODIFIED" in msg:
            return None
    return event


def capture_exception(exc: Exception, context: dict | None = None) -> None:
    """Хелпер для логування винятків з контекстом (handle-and-continue)."""
    try:
        import sentry_sdk
        if context:
            with sentry_sdk.push_scope() as scope:
                for k, v in context.items():
                    scope.set_extra(k, v)
                sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass
