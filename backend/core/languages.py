LANGUAGES = {
    "uk": ("Українська", "🇺🇦"),
    "en": ("English", "🇬🇧"),
    "es": ("Español", "🇪🇸"),
    "pl": ("Polski", "🇵🇱"),
    "de": ("Deutsch", "🇩🇪"),
}


def lang_flag(code: str) -> str:
    return LANGUAGES.get(code, ("?", "🌐"))[1]


def lang_name(code: str) -> str:
    return LANGUAGES.get(code, ("?", "🌐"))[0]
