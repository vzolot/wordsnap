"""
Локалізація бот-повідомлень для 4 мов.
"""
from typing import Any

from .languages import lang_flag, lang_name

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
    },
}


def t(key: str, lang: str = "uk", **vars: Any) -> str:
    dict_ = T.get(lang) or T["uk"]
    s = dict_.get(key) or T["uk"].get(key) or key
    for k, v in vars.items():
        s = s.replace("{" + k + "}", str(v))
    return s
