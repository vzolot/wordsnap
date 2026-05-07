"""Avatar emoji helpers.

Кожен юзер може вибрати свій avatar_emoji у Settings. Якщо не вибрано —
повертаємо детермінований дефолт з telegram_id (щоб у leaderboard у юзера
завжди був стабільний аватар, навіть до першого вибору).
"""

# 32 нейтральних, дружніх емодзі — переважно тварини. Підбірка має бути
# крос-платформенно стабільна (всі рендеряться однаково на iOS/Android/Web).
AVATAR_EMOJIS: list[str] = [
    "🐱", "🐶", "🦊", "🐼", "🐰", "🐨", "🐯", "🦁",
    "🐮", "🐷", "🐸", "🐵", "🐔", "🐧", "🦉", "🦅",
    "🦄", "🐲", "🦋", "🐢", "🦖", "🐬", "🐳", "🦜",
    "🐝", "🐞", "🦂", "🦑", "🦐", "🐍", "🦔", "🦦",
]

ALLOWED_AVATARS: frozenset[str] = frozenset(AVATAR_EMOJIS)


def default_avatar(telegram_id: int) -> str:
    """Стабільний дефолт від telegram_id — той самий емодзі для одного юзера."""
    return AVATAR_EMOJIS[telegram_id % len(AVATAR_EMOJIS)]


def resolve_avatar(avatar_emoji: str | None, telegram_id: int) -> str:
    """Повертає емодзі юзера або дефолтний по telegram_id."""
    if avatar_emoji and avatar_emoji in ALLOWED_AVATARS:
        return avatar_emoji
    return default_avatar(telegram_id)
