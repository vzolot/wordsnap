"""
Куровані набори слів з популярних пісень — для швидкого старту вивчення.
Ключ — target_lang (мова, яку юзер вивчає).
"""

SONG_PACKS = {
    "en": [
        {
            "id": "en-imagine",
            "title": "Imagine",
            "artist": "John Lennon",
            "emoji": "🕊️",
            "words": ["imagine", "heaven", "peace", "dreamer", "brotherhood",
                      "possessions", "above us", "share the world", "join us"],
        },
        {
            "id": "en-hello",
            "title": "Hello",
            "artist": "Adele",
            "emoji": "📞",
            "words": ["wondering", "outside", "calling", "thousand times",
                      "tear apart", "regret", "at least", "different"],
        },
        {
            "id": "en-yesterday",
            "title": "Yesterday",
            "artist": "The Beatles",
            "emoji": "🌅",
            "words": ["yesterday", "troubles", "far away", "shadow",
                      "suddenly", "believe", "place to hide", "wrong"],
        },
        {
            "id": "en-perfect",
            "title": "Perfect",
            "artist": "Ed Sheeran",
            "emoji": "💕",
            "words": ["perfect", "darling", "sweetheart", "underneath",
                      "barefoot", "stranger", "carry", "whisper"],
        },
    ],
    "es": [
        {
            "id": "es-despacito",
            "title": "Despacito",
            "artist": "Luis Fonsi",
            "emoji": "💃",
            "words": ["despacito", "suavecito", "respiro", "lentamente",
                      "abrazos", "firmar", "rincón", "labios"],
        },
        {
            "id": "es-vivir",
            "title": "Vivir Mi Vida",
            "artist": "Marc Anthony",
            "emoji": "🌞",
            "words": ["vivir", "reír", "celebrar", "lloraré",
                      "soñar", "agradecer", "camino", "alegría"],
        },
        {
            "id": "es-bailando",
            "title": "Bailando",
            "artist": "Enrique Iglesias",
            "emoji": "🕺",
            "words": ["bailando", "ritmo", "corazón", "abrázame",
                      "lentamente", "respirar", "olvidar", "sentir"],
        },
    ],
    "pl": [
        {
            "id": "pl-kasztany",
            "title": "Kasztany",
            "artist": "Maciej Maleńczuk",
            "emoji": "🌰",
            "words": ["kasztany", "spadają", "jesień", "dziewczyna",
                      "spojrzenie", "wspomnienia", "wracać", "tęsknota"],
        },
        {
            "id": "pl-warszawa",
            "title": "Warszawa",
            "artist": "T.Love",
            "emoji": "🏙️",
            "words": ["miasto", "ulica", "świt", "tańczyć",
                      "pamiętać", "wiosna", "deszcz"],
        },
        {
            "id": "pl-szczescie",
            "title": "Małe Szczęścia",
            "artist": "Sylwia Grzeszczak",
            "emoji": "✨",
            "words": ["szczęście", "uśmiech", "drobne rzeczy", "uwierzyć",
                      "marzenie", "spokój", "radość"],
        },
    ],
    "de": [
        {
            "id": "de-99",
            "title": "99 Luftballons",
            "artist": "Nena",
            "emoji": "🎈",
            "words": ["Luftballon", "Horizont", "Krieg", "Frieden",
                      "Soldat", "Pilot", "Feuerwerk", "verlieren"],
        },
        {
            "id": "de-atemlos",
            "title": "Atemlos durch die Nacht",
            "artist": "Helene Fischer",
            "emoji": "🌙",
            "words": ["atemlos", "Herz", "Gefühl", "Sehnsucht",
                      "fliegen", "wachsen", "ewig", "still"],
        },
        {
            "id": "de-uber-den-wolken",
            "title": "Über den Wolken",
            "artist": "Reinhard Mey",
            "emoji": "☁️",
            "words": ["Wolke", "grenzenlos", "Freiheit", "Sorge",
                      "Angst", "klein", "Erde", "Traum"],
        },
    ],
    "uk": [
        {
            "id": "uk-chervona-ruta",
            "title": "Червона рута",
            "artist": "Володимир Івасюк",
            "emoji": "🌹",
            "words": ["рута", "знайти", "вечір", "очі",
                      "любов", "квіти", "серце", "обличчя"],
        },
        {
            "id": "uk-vse-bude-dobre",
            "title": "Все буде добре",
            "artist": "Океан Ельзи",
            "emoji": "🌅",
            "words": ["вірити", "дочекатись", "сонце", "небо",
                      "майбутнє", "обійми", "шлях"],
        },
        {
            "id": "uk-okean",
            "title": "Така як ти",
            "artist": "Океан Ельзи",
            "emoji": "💜",
            "words": ["погляд", "ніжність", "посмішка", "доля",
                      "вірність", "тиша", "знову"],
        },
    ],
}


def get_packs(target_lang: str) -> list:
    return SONG_PACKS.get(target_lang, [])


def get_pack(target_lang: str, pack_id: str) -> dict | None:
    for p in SONG_PACKS.get(target_lang, []):
        if p["id"] == pack_id:
            return p
    return None
