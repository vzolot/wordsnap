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
            {"sentence": "Czy chce Pan paragon?", "explanation": "kasjer pyta przy płatności"},
            {"sentence": "Proszę paragon", "explanation": "uprzejma prośba o wydanie"},
            {"sentence": "Zgubiłem paragon", "explanation": "informujesz, że nie masz dowodu zakupu"},
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
            {"sentence": "Ich brauche einen Termin", "explanation": "du fragst nach einem Slot"},
            {"sentence": "Haben Sie einen Termin?", "explanation": "Empfang prüft deine Buchung"},
            {"sentence": "Der Termin ist abgesagt", "explanation": "der Termin wurde storniert"},
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
            {"sentence": "La cuenta, por favor", "explanation": "lo dices al camarero al final"},
            {"sentence": "¿Me trae la cuenta?", "explanation": "pides educadamente que la traigan"},
            {"sentence": "¿Pagamos por separado?", "explanation": "preguntas si dividir el pago"},
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
            {"sentence": "I'm applying for a mortgage", "explanation": "submitting paperwork to a bank"},
            {"sentence": "Mortgage rates are up", "explanation": "interest cost has risen"},
            {"sentence": "How much is your mortgage?", "explanation": "asking about monthly payment"},
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
