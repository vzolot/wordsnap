"""Snap зі скріншоту / голосової — нові точки входу.

Юзер шле:
  - фото переписки → vision-екстракт → пропоную до 8 слів кнопками
  - голосову → Whisper-транскрипт → той самий екстракт

Тап по кнопці запускає той самий add-pipeline що і ручний ввід тексту
(`can_add_word` → `get_word_data` + image → `save_word`), отже всі ліміти,
кеш AI, картинки з Unsplash працюють тут безкоштовно.
"""
import asyncio
import base64
import logging
from html import escape
from io import BytesIO

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message

from core import analytics
from core.bot_i18n import t as bt
from core.openai_client import (
    extract_words_from_image,
    extract_words_from_transcript,
    get_word_data,
    transcribe_voice,
)
from core.unsplash_client import search_image
from core.user_service import can_add_word, get_or_create_user, increment_word_counter
from core.word_service import save_word, word_exists
from core.bot_registry import tenant_id_for_bot
from bot.keyboards.snap_keyboards import snap_extract_keyboard

logger = logging.getLogger(__name__)
router = Router()


async def _resolve_user_from(tg_user, tenant_id: int = 1):
    """Build/fetch wordsnap User з aiogram tg-user об'єкта (у межах тенанта).

    Важливо: у callback_query треба передавати `callback.from_user`, а НЕ
    `callback.message.from_user` — друге це сам бот (бо повідомлення
    прислав він), і ми б шукали юзера з telegram_id бота, що завжди дає
    target_lang=None і silently ретернить. Звідси «кнопка не реагує».
    """
    if tg_user is None:
        return None, None
    user = await get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        language_code=tg_user.language_code,
        tenant_id=tenant_id,
    )
    return user, user.native_lang or "en"


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    """Фото → vision-екстракт → клавіатура з кандидатами."""
    # тенант цього бота (мультитенантність)
    user, lang = await _resolve_user_from(message.from_user, tenant_id_for_bot(message.bot))
    if user is None:
        return

    if not user.target_lang:
        await message.answer(bt("word.setup_first", lang))
        return

    await message.bot.send_chat_action(
        chat_id=message.chat.id, action=ChatAction.TYPING
    )

    try:
        # Беремо найбільший варіант (Telegram присилає 4 розміри).
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        buf = BytesIO()
        await message.bot.download_file(file.file_path, buf)
        image_bytes = buf.getvalue()
    except Exception as e:
        logger.warning("snap photo download failed: %s", e)
        await message.answer(bt("snap.download_failed", lang))
        return

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    try:
        words = await extract_words_from_image(
            image_b64,
            target_lang=user.target_lang,
            native_lang=user.native_lang or "en",
        )
    except Exception as e:
        logger.warning("snap photo extract failed: %s", e)
        words = []

    analytics.capture(message.from_user.id, "snap_extracted", {
        "source": "photo",
        "n_words": len(words),
        "target_lang": user.target_lang,
    })

    if not words:
        await message.answer(bt("snap.empty", lang))
        return

    text = bt("snap.found_n", lang, n=len(words))
    await message.answer(
        text,
        reply_markup=snap_extract_keyboard(words, source="photo"),
    )


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    """Голосова → Whisper → екстракт → клавіатура з кандидатами."""
    # тенант цього бота (мультитенантність)
    user, lang = await _resolve_user_from(message.from_user, tenant_id_for_bot(message.bot))
    if user is None:
        return

    if not user.target_lang:
        await message.answer(bt("word.setup_first", lang))
        return

    await message.bot.send_chat_action(
        chat_id=message.chat.id, action=ChatAction.TYPING
    )

    try:
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        buf = BytesIO()
        await message.bot.download_file(file.file_path, buf)
        audio_bytes = buf.getvalue()
    except Exception as e:
        logger.warning("snap voice download failed: %s", e)
        await message.answer(bt("snap.download_failed", lang))
        return

    transcript, detected_lang = await transcribe_voice(
        audio_bytes, filename="voice.ogg"
    )
    if not transcript:
        await message.answer(bt("snap.transcribe_failed", lang))
        return

    words = await extract_words_from_transcript(
        transcript,
        target_lang=user.target_lang,
        native_lang=user.native_lang or "en",
    )

    analytics.capture(message.from_user.id, "snap_extracted", {
        "source": "voice",
        "n_words": len(words),
        "target_lang": user.target_lang,
        "detected_lang": detected_lang,
        "transcript_len": len(transcript),
    })

    # Покажемо короткий transcript-preview, щоб юзер бачив що ми зрозуміли.
    preview = escape(transcript[:200] + ("…" if len(transcript) > 200 else ""))
    head = bt("snap.voice_transcript", lang, preview=preview)

    if not words:
        # voice_no_words — окремий ключ, бо `snap.empty` згадує «фото».
        await message.answer(head + "\n\n" + bt("snap.voice_no_words", lang))
        return

    await message.answer(
        head + "\n\n" + bt("snap.found_n", lang, n=len(words)),
        reply_markup=snap_extract_keyboard(words, source="voice"),
    )


@router.callback_query(F.data.startswith("snap_add:"))
async def cb_snap_add(callback: CallbackQuery) -> None:
    """Тап «➕ слово» — той самий add-pipeline що ручний ввід.

    callback_data: `snap_add:<source>:<word>`.
    """
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return
    _, source, word = parts
    word = word.strip().lower()
    if not word:
        await callback.answer()
        return

    # `callback.from_user` — це людина, що натиснула. `callback.message.from_user`
    # був би сам бот — старий баг через який кнопка тихо нічого не робила.
    # тенант цього бота (мультитенантність)
    user, lang = await _resolve_user_from(callback.from_user, tenant_id_for_bot(callback.bot))
    if user is None:
        await callback.answer()
        return
    if not user.target_lang:
        await callback.answer(bt("word.setup_first", lang), show_alert=True)
        return

    can_add, reason = await can_add_word(user, lang)
    if not can_add:
        from datetime import datetime, timezone, timedelta
        is_trial_now = bool(
            user.created_at
            and (datetime.now(timezone.utc) - user.created_at) < timedelta(days=7)
        )
        is_pro_now = (
            user.plan == "pro"
            and user.plan_expires_at
            and user.plan_expires_at > datetime.now(timezone.utc)
        )
        period = "day" if (is_pro_now or is_trial_now) else "week"
        analytics.capture(callback.from_user.id, "paywall_hit", {
            "reason": f"{period}_limit",
            "period": period,
            "plan": user.plan or "free",
            "source": f"snap_{source}",
        })
        await callback.answer(bt("snap.limit_short", lang), show_alert=True)
        # Повний текст ліміту як окреме повідомлення для деталей.
        try:
            await callback.message.answer(reason)
        except Exception:
            pass
        return

    if await word_exists(user.id, word, user.target_lang):
        # Modal alert (was a silent toast — users tapped duplicates and thought
        # the bot was broken because nothing visible happened).
        await callback.answer(bt("snap.duplicate_short", lang), show_alert=True)
        return

    await callback.answer(bt("snap.adding", lang))
    await callback.message.bot.send_chat_action(
        chat_id=callback.message.chat.id, action=ChatAction.TYPING
    )

    # AI + Unsplash паралельно — точно як у word_handler/api_routes.
    ai_task = asyncio.create_task(
        get_word_data(word, target_lang=user.target_lang, native_lang=lang)
    )
    image_task = asyncio.create_task(search_image(word))

    ai_data = await ai_task
    if not ai_data:
        image_task.cancel()
        await callback.message.answer(bt("snap.ai_failed", lang, word=escape(word)))
        return
    if ai_data.get("is_real") is False:
        image_task.cancel()
        analytics.capture(callback.from_user.id, "word_rejected", {
            "target_lang": user.target_lang,
            "reason": "not_real",
            "source": f"snap_{source}",
        })
        await callback.message.answer(bt("snap.not_real", lang, word=escape(word)))
        return

    image_url = await image_task

    saved = await save_word(
        user_id=user.id,
        word=word,
        target_lang=user.target_lang,
        ai_data=ai_data,
        image_url=image_url,
        tenant_id=user.tenant_id,
    )
    if not saved:
        await callback.message.answer(bt("snap.save_failed", lang))
        return

    await increment_word_counter(user.telegram_id, tenant_id=user.tenant_id)
    analytics.capture(callback.from_user.id, "word_added", {
        "target_lang": user.target_lang,
        "native_lang": user.native_lang,
        "has_image": bool(image_url),
        "source": f"snap_{source}",
    })

    translation = escape(ai_data.get("translation") or "")
    await callback.message.answer(
        bt("snap.added_ok", lang, word=escape(word), translation=translation)
    )
