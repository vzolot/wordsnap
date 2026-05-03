"""
Локалізація бот-повідомлень для 5 мов.
"""
from typing import Any

T = {
    "uk": {
        "setup.saved": "✅ <b>Налаштування збережено!</b>",
        "setup.native": "🏠 Рідна мова",
        "setup.target": "🎯 Вивчаємо",
        "setup.how_to_use": "<b>Як хочеш користуватись:</b>",
        "setup.via_chat": "💬 <b>У чаті</b> — просто надсилай слова сюди, бот робить переклад і нагадування",
        "setup.via_app": "📱 <b>У додатку</b> — натисни кнопку нижче, додавай і повторюй у зручному UI",
        "setup.synced": "<i>Можеш користуватись і там, і там — усе синхронізовано.</i>",
        "setup.change_lang": "<i>Змінити мови: /language</i>",
        "setup.open_app": "📱 Відкрити WordSnap App",
        "setup.ask_native": "🌍 <b>Яка твоя рідна мова?</b>\n\n<i>Переклади будуть показані цією мовою.</i>",
        "setup.ask_target": "✅ Рідна мова: <b>{flag} {name}</b>\n\n🎯 <b>Яку мову хочеш вивчати?</b>",

        "help.title": "❓ <b>Команди WordSnap</b>",
        "help.learning": "<b>Навчання:</b>",
        "help.send_words": "• Просто надсилай слова — я перекладу",
        "help.review": "• /review — повторити слова зараз",
        "help.songs": "• /songs — слова з популярних пісень 🎵",
        "help.app": "• /app — відкрити міні-додаток",
        "help.stats": "• /stats — твоя статистика",
        "help.language": "• /language — змінити мову навчання",
        "help.subscription_title": "<b>Підписка:</b>",
        "help.premium": "• /premium — інфо про Pro",
        "help.buy": "• /buy — оформити Pro",
        "help.subscription": "• /subscription — статус підписки",
        "help.unsubscribe": "• /unsubscribe — скасувати автопродовження",
        "help.plans": "<b>Free:</b> 10 слів/день\n<b>Pro:</b> 100 слів/день, $1.49/міс",

        "app.intro": "📱 <b>Відкрий WordSnap App</b>\n\nДодавай слова, повторюй у зручному інтерфейсі, відстежуй прогрес.",
        "settings.title": "⚙️ <b>Налаштування</b>",
        "settings.lang_btn": "🌐 Мова навчання",
        "settings.app_btn": "📱 Відкрити додаток",

        "songs.title": "🎵 <b>Слова з популярних пісень</b>\n\nТапни на пісню — побачиш ключові слова. Натиснеш на слово — додам у твій словник.",
        "songs.empty": "🎵 Поки немає підборок для цієї мови. Скоро додамо!",
        "songs.song_intro": "{emoji} <b>{title}</b>\n<i>{artist}</i>\n\nТапни слово, щоб додати у твій словник:",
        "songs.back": "← Назад до пісень",
        "songs.duplicate_alert": "Це слово вже є у твоєму словнику",
        "songs.limit_alert": "Денний ліміт вичерпано",
        "songs.adding": "Додаю…",
        "songs.added_inline": "✅ Додано: {word}",
    },
    "en": {
        "setup.saved": "✅ <b>Setup saved!</b>",
        "setup.native": "🏠 Native language",
        "setup.target": "🎯 Learning",
        "setup.how_to_use": "<b>How to use:</b>",
        "setup.via_chat": "💬 <b>In chat</b> — just send words here, the bot translates and reminds",
        "setup.via_app": "📱 <b>In the app</b> — tap the button below to add and review in a nice UI",
        "setup.synced": "<i>Use either or both — everything is synced.</i>",
        "setup.change_lang": "<i>Change languages: /language</i>",
        "setup.open_app": "📱 Open WordSnap App",
        "setup.ask_native": "🌍 <b>What is your native language?</b>\n\n<i>Translations will be shown in this language.</i>",
        "setup.ask_target": "✅ Native: <b>{flag} {name}</b>\n\n🎯 <b>Which language do you want to learn?</b>",

        "help.title": "❓ <b>WordSnap Commands</b>",
        "help.learning": "<b>Learning:</b>",
        "help.send_words": "• Just send words — I'll translate",
        "help.review": "• /review — review words now",
        "help.songs": "• /songs — words from popular songs 🎵",
        "help.app": "• /app — open the mini app",
        "help.stats": "• /stats — your stats",
        "help.language": "• /language — change learning language",
        "help.subscription_title": "<b>Subscription:</b>",
        "help.premium": "• /premium — Pro info",
        "help.buy": "• /buy — get Pro",
        "help.subscription": "• /subscription — subscription status",
        "help.unsubscribe": "• /unsubscribe — cancel auto-renewal",
        "help.plans": "<b>Free:</b> 10 words/day\n<b>Pro:</b> 100 words/day, $1.49/mo",

        "app.intro": "📱 <b>Open the WordSnap App</b>\n\nAdd words, review in a comfortable UI, track your progress.",
        "settings.title": "⚙️ <b>Settings</b>",
        "settings.lang_btn": "🌐 Learning language",
        "settings.app_btn": "📱 Open the app",

        "songs.title": "🎵 <b>Vocabulary from popular songs</b>\n\nTap a song to see its key words. Tap a word — I'll add it to your vocabulary.",
        "songs.empty": "🎵 No song packs for this language yet. Coming soon!",
        "songs.song_intro": "{emoji} <b>{title}</b>\n<i>{artist}</i>\n\nTap a word to add it to your vocabulary:",
        "songs.back": "← Back to songs",
        "songs.duplicate_alert": "This word is already in your vocabulary",
        "songs.limit_alert": "Daily limit reached",
        "songs.adding": "Adding…",
        "songs.added_inline": "✅ Added: {word}",
    },
    "es": {
        "setup.saved": "✅ <b>¡Configuración guardada!</b>",
        "setup.native": "🏠 Idioma nativo",
        "setup.target": "🎯 Estudiando",
        "setup.how_to_use": "<b>Cómo usar:</b>",
        "setup.via_chat": "💬 <b>En el chat</b> — envía palabras aquí, el bot traduce y recuerda",
        "setup.via_app": "📱 <b>En la app</b> — pulsa el botón de abajo para añadir y repasar con UI cómoda",
        "setup.synced": "<i>Usa cualquiera de los dos — todo está sincronizado.</i>",
        "setup.change_lang": "<i>Cambiar idiomas: /language</i>",
        "setup.open_app": "📱 Abrir WordSnap App",
        "setup.ask_native": "🌍 <b>¿Cuál es tu idioma nativo?</b>\n\n<i>Las traducciones se mostrarán en este idioma.</i>",
        "setup.ask_target": "✅ Nativo: <b>{flag} {name}</b>\n\n🎯 <b>¿Qué idioma quieres aprender?</b>",

        "help.title": "❓ <b>Comandos de WordSnap</b>",
        "help.learning": "<b>Aprendizaje:</b>",
        "help.send_words": "• Solo envía palabras — yo traduzco",
        "help.review": "• /review — repasar palabras ahora",
        "help.songs": "• /songs — palabras de canciones populares 🎵",
        "help.app": "• /app — abrir la mini-app",
        "help.stats": "• /stats — tus estadísticas",
        "help.language": "• /language — cambiar idioma de aprendizaje",
        "help.subscription_title": "<b>Suscripción:</b>",
        "help.premium": "• /premium — info Pro",
        "help.buy": "• /buy — obtener Pro",
        "help.subscription": "• /subscription — estado de la suscripción",
        "help.unsubscribe": "• /unsubscribe — cancelar renovación automática",
        "help.plans": "<b>Free:</b> 10 palabras/día\n<b>Pro:</b> 100 palabras/día, $1.49/mes",

        "app.intro": "📱 <b>Abre WordSnap App</b>\n\nAñade palabras, repasa en una UI cómoda, sigue tu progreso.",
        "settings.title": "⚙️ <b>Ajustes</b>",
        "settings.lang_btn": "🌐 Idioma de aprendizaje",
        "settings.app_btn": "📱 Abrir la app",

        "songs.title": "🎵 <b>Vocabulario de canciones populares</b>\n\nToca una canción para ver sus palabras clave. Toca una palabra y la añadiré a tu vocabulario.",
        "songs.empty": "🎵 Aún no hay packs para este idioma. ¡Pronto!",
        "songs.song_intro": "{emoji} <b>{title}</b>\n<i>{artist}</i>\n\nToca una palabra para añadirla:",
        "songs.back": "← Volver a canciones",
        "songs.duplicate_alert": "Ya tienes esta palabra",
        "songs.limit_alert": "Límite diario alcanzado",
        "songs.adding": "Añadiendo…",
        "songs.added_inline": "✅ Añadida: {word}",
    },
    "pl": {
        "setup.saved": "✅ <b>Ustawienia zapisane!</b>",
        "setup.native": "🏠 Język ojczysty",
        "setup.target": "🎯 Uczę się",
        "setup.how_to_use": "<b>Jak korzystać:</b>",
        "setup.via_chat": "💬 <b>Na czacie</b> — wysyłaj słowa tutaj, bot tłumaczy i przypomina",
        "setup.via_app": "📱 <b>W aplikacji</b> — naciśnij przycisk poniżej, by dodawać i powtarzać w wygodnym UI",
        "setup.synced": "<i>Możesz korzystać z obu — wszystko jest zsynchronizowane.</i>",
        "setup.change_lang": "<i>Zmień języki: /language</i>",
        "setup.open_app": "📱 Otwórz WordSnap App",
        "setup.ask_native": "🌍 <b>Jaki jest Twój język ojczysty?</b>\n\n<i>Tłumaczenia będą pokazane w tym języku.</i>",
        "setup.ask_target": "✅ Język ojczysty: <b>{flag} {name}</b>\n\n🎯 <b>Jakiego języka chcesz się uczyć?</b>",

        "help.title": "❓ <b>Polecenia WordSnap</b>",
        "help.learning": "<b>Nauka:</b>",
        "help.send_words": "• Po prostu wysyłaj słowa — przetłumaczę",
        "help.review": "• /review — powtórzyć teraz",
        "help.songs": "• /songs — słowa z popularnych piosenek 🎵",
        "help.app": "• /app — otwórz mini-aplikację",
        "help.stats": "• /stats — twoje statystyki",
        "help.language": "• /language — zmień język nauki",
        "help.subscription_title": "<b>Subskrypcja:</b>",
        "help.premium": "• /premium — info Pro",
        "help.buy": "• /buy — kup Pro",
        "help.subscription": "• /subscription — status subskrypcji",
        "help.unsubscribe": "• /unsubscribe — anuluj odnawianie",
        "help.plans": "<b>Free:</b> 10 słów/dzień\n<b>Pro:</b> 100 słów/dzień, $1.49/mc",

        "app.intro": "📱 <b>Otwórz WordSnap App</b>\n\nDodawaj słowa, powtarzaj w wygodnym UI, śledź postępy.",
        "settings.title": "⚙️ <b>Ustawienia</b>",
        "settings.lang_btn": "🌐 Język nauki",
        "settings.app_btn": "📱 Otwórz aplikację",

        "songs.title": "🎵 <b>Słownictwo z popularnych piosenek</b>\n\nDotknij piosenki, by zobaczyć kluczowe słowa. Dotknij słowa — dodam je do słownika.",
        "songs.empty": "🎵 Nie ma jeszcze paczek dla tego języka. Wkrótce!",
        "songs.song_intro": "{emoji} <b>{title}</b>\n<i>{artist}</i>\n\nDotknij słowa, by dodać je do słownika:",
        "songs.back": "← Wróć do piosenek",
        "songs.duplicate_alert": "Masz już to słowo",
        "songs.limit_alert": "Dzienny limit wyczerpany",
        "songs.adding": "Dodaję…",
        "songs.added_inline": "✅ Dodano: {word}",
    },
    "de": {
        "setup.saved": "✅ <b>Einstellungen gespeichert!</b>",
        "setup.native": "🏠 Muttersprache",
        "setup.target": "🎯 Lernen",
        "setup.how_to_use": "<b>So benutzt du es:</b>",
        "setup.via_chat": "💬 <b>Im Chat</b> — sende einfach Wörter hierher, der Bot übersetzt und erinnert",
        "setup.via_app": "📱 <b>In der App</b> — tippe unten, um Wörter in einer schönen UI hinzuzufügen und zu wiederholen",
        "setup.synced": "<i>Nutze beides — alles ist synchronisiert.</i>",
        "setup.change_lang": "<i>Sprachen ändern: /language</i>",
        "setup.open_app": "📱 WordSnap App öffnen",
        "setup.ask_native": "🌍 <b>Was ist deine Muttersprache?</b>\n\n<i>Übersetzungen werden in dieser Sprache angezeigt.</i>",
        "setup.ask_target": "✅ Muttersprache: <b>{flag} {name}</b>\n\n🎯 <b>Welche Sprache möchtest du lernen?</b>",

        "help.title": "❓ <b>WordSnap Befehle</b>",
        "help.learning": "<b>Lernen:</b>",
        "help.send_words": "• Sende einfach Wörter — ich übersetze",
        "help.review": "• /review — jetzt wiederholen",
        "help.songs": "• /songs — Wörter aus beliebten Liedern 🎵",
        "help.app": "• /app — Mini-App öffnen",
        "help.stats": "• /stats — deine Statistik",
        "help.language": "• /language — Lernsprache ändern",
        "help.subscription_title": "<b>Abo:</b>",
        "help.premium": "• /premium — Pro-Info",
        "help.buy": "• /buy — Pro holen",
        "help.subscription": "• /subscription — Abo-Status",
        "help.unsubscribe": "• /unsubscribe — Auto-Verlängerung kündigen",
        "help.plans": "<b>Free:</b> 10 Wörter/Tag\n<b>Pro:</b> 100 Wörter/Tag, $1.49/Mon.",

        "app.intro": "📱 <b>Öffne die WordSnap App</b>\n\nFüge Wörter hinzu, wiederhole in einer schönen UI, verfolge deinen Fortschritt.",
        "settings.title": "⚙️ <b>Einstellungen</b>",
        "settings.lang_btn": "🌐 Lernsprache",
        "settings.app_btn": "📱 App öffnen",

        "songs.title": "🎵 <b>Vokabeln aus beliebten Liedern</b>\n\nTippe ein Lied, um die Schlüsselwörter zu sehen. Tippe ein Wort — ich füge es deinem Wortschatz hinzu.",
        "songs.empty": "🎵 Noch keine Packs für diese Sprache. Bald!",
        "songs.song_intro": "{emoji} <b>{title}</b>\n<i>{artist}</i>\n\nTippe ein Wort, um es hinzuzufügen:",
        "songs.back": "← Zurück zu Liedern",
        "songs.duplicate_alert": "Du hast dieses Wort bereits",
        "songs.limit_alert": "Tageslimit erreicht",
        "songs.adding": "Hinzufügen…",
        "songs.added_inline": "✅ Hinzugefügt: {word}",
    },
}


def t(key: str, lang: str = "uk", **vars: Any) -> str:
    dict_ = T.get(lang) or T["uk"]
    s = dict_.get(key) or T["uk"].get(key) or key
    for k, v in vars.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def help_text(lang: str = "uk") -> str:
    return (
        f"{t('help.title', lang)}\n\n"
        f"{t('help.learning', lang)}\n"
        f"{t('help.send_words', lang)}\n"
        f"{t('help.songs', lang)}\n"
        f"{t('help.review', lang)}\n"
        f"{t('help.app', lang)}\n"
        f"{t('help.stats', lang)}\n"
        f"{t('help.language', lang)}\n\n"
        f"{t('help.subscription_title', lang)}\n"
        f"{t('help.premium', lang)}\n"
        f"{t('help.buy', lang)}\n"
        f"{t('help.subscription', lang)}\n"
        f"{t('help.unsubscribe', lang)}\n\n"
        f"{t('help.plans', lang)}"
    )
