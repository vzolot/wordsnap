// Озвучення слів через нативний браузерний speechSynthesis API.
// Безкоштовно, працює офлайн на більшості сучасних пристроїв.
//
// На iOS Telegram WebView голоси можуть зʼявитися з затримкою —
// тому слухаємо `voiceschanged` і кешуємо при першій же доступності.

const LANG_LOCALES = {
  uk: ['uk-UA', 'uk'],
  en: ['en-US', 'en-GB', 'en'],
  es: ['es-ES', 'es-MX', 'es-US', 'es'],
  pl: ['pl-PL', 'pl'],
  de: ['de-DE', 'de-AT', 'de-CH', 'de'],
};

let voicesCache = [];

function refreshVoices() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return;
  const v = window.speechSynthesis.getVoices();
  if (v && v.length) voicesCache = v;
}

if (typeof window !== 'undefined' && window.speechSynthesis) {
  refreshVoices();
  // Chrome lazy-loads voices, Safari iOS теж може
  window.speechSynthesis.addEventListener?.('voiceschanged', refreshVoices);
}

function pickVoice(langCode) {
  if (!voicesCache.length) refreshVoices();
  const locales = LANG_LOCALES[langCode] || [langCode];
  for (const loc of locales) {
    const exact = voicesCache.find(v => v.lang === loc);
    if (exact) return exact;
  }
  // Префікс-матч (наприклад "es-AR" якщо просили "es-ES")
  const base = (langCode || '').toLowerCase();
  return voicesCache.find(v => v.lang?.toLowerCase().startsWith(base + '-')) || null;
}

export function isSpeechSupported() {
  return typeof window !== 'undefined'
    && !!window.speechSynthesis
    && typeof window.SpeechSynthesisUtterance === 'function';
}

export function speak(text, langCode) {
  if (!isSpeechSupported() || !text) return;
  const synth = window.speechSynthesis;
  // Скасовуємо попереднє щоб не було накладень якщо юзер тапає швидко
  try { synth.cancel(); } catch { /* noop */ }

  const utter = new SpeechSynthesisUtterance(String(text));
  const voice = pickVoice(langCode);
  if (voice) {
    utter.voice = voice;
    utter.lang = voice.lang;
  } else {
    const locales = LANG_LOCALES[langCode] || [langCode];
    if (locales[0]) utter.lang = locales[0];
  }
  // Трохи повільніше — зручніше для вивчення
  utter.rate = 0.92;
  utter.pitch = 1;

  try {
    synth.speak(utter);
  } catch { /* noop */ }
}
