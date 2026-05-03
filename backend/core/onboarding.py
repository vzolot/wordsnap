"""
Дані для onboarding-флоу:
- Список міст за target_lang (для питання «Де живеш?»)
- Демо-слова для першого snap (поки тільки для UA-native, інші — fallback)

Демо-слова повертаються у тому ж форматі, що й OpenAI-відповідь для add_word,
тому save_word приймає їх без змін.
"""

# Міста (id, label) для кожного target_lang. id зберігається в users.region.
CITIES = {
    "pl": [("warsaw", "Warszawa"), ("krakow", "Kraków"), ("wroclaw", "Wrocław")],
    "de": [("berlin", "Berlin"), ("munich", "München"), ("vienna", "Wien")],
    "es": [("madrid", "Madrid"), ("barcelona", "Barcelona"), ("valencia", "Valencia")],
    "en": [("london", "London"), ("dublin", "Dublin"), ("toronto", "Toronto")],
    "uk": [("kyiv", "Київ"), ("lviv", "Львів"), ("odesa", "Одеса")],
}


# Демо-слова за target_lang. Переклади поки в UA — для української цільової
# аудиторії. Для не-UA natives демо-snap пропускається.
DEMO_WORDS_UK = {
    "pl": {
        "word": "paragon",
        "translation": "чек (від покупки)",
        "part_of_speech": "noun",
        "difficulty": "A2",
        "examples": [
            {"sentence": "Czy chce Pan paragon?", "explanation": "Бажаєте чек?"},
            {"sentence": "Proszę paragon", "explanation": "Дайте, будь ласка, чек."},
            {"sentence": "Zgubiłem paragon", "explanation": "Я загубив чек."},
        ],
        "memory_tip": "Як «фрагмент» — клаптик паперу з покупки.",
        "image_keyword": "receipt",
    },
    "de": {
        "word": "Termin",
        "translation": "запис, прийом (на конкретний час)",
        "part_of_speech": "noun",
        "difficulty": "A2",
        "examples": [
            {"sentence": "Ich brauche einen Termin", "explanation": "Мені потрібен запис."},
            {"sentence": "Haben Sie einen Termin?", "explanation": "У вас є запис?"},
            {"sentence": "Der Termin ist abgesagt", "explanation": "Зустріч скасована."},
        ],
        "memory_tip": "Корінь «term» — як «термін» у нас.",
        "image_keyword": "calendar appointment",
    },
    "es": {
        "word": "la cuenta",
        "translation": "рахунок (у барі/ресторані)",
        "part_of_speech": "noun",
        "difficulty": "A1",
        "examples": [
            {"sentence": "La cuenta, por favor", "explanation": "Рахунок, будь ласка."},
            {"sentence": "¿Me trae la cuenta?", "explanation": "Принесете рахунок?"},
            {"sentence": "¿Pagamos por separado?", "explanation": "Платимо окремо?"},
        ],
        "memory_tip": "Як «count» / «cuenta» — те, що рахує касир.",
        "image_keyword": "restaurant bill",
    },
    "en": {
        "word": "mortgage",
        "translation": "іпотечний кредит",
        "part_of_speech": "noun",
        "difficulty": "B2",
        "examples": [
            {"sentence": "I'm applying for a mortgage", "explanation": "Я подаюся на іпотеку."},
            {"sentence": "Mortgage rates are up", "explanation": "Іпотечні ставки виросли."},
            {"sentence": "How much is your mortgage?", "explanation": "Скільки в тебе іпотека?"},
        ],
        "memory_tip": "«mort» — мертве заставне зобов'язання, фінансовий термін.",
        "image_keyword": "house mortgage",
    },
}


def get_demo_word(target_lang: str, native_lang: str) -> dict | None:
    """Повертає демо-слово для пари (target, native). None — пропустити демо."""
    if native_lang == "uk":
        return DEMO_WORDS_UK.get(target_lang)
    return None


def get_cities(target_lang: str) -> list[tuple[str, str]]:
    return CITIES.get(target_lang, [])
