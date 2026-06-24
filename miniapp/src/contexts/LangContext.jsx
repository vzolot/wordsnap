import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getStats, getTelegramUserId } from '../api/client';
import { detectLang, plural as pluralFn, SUPPORTED_LANGS, t as tFn } from '../i18n';

const LangContext = createContext({ lang: 'en', setLang: () => {}, loaded: false });

// v2 storage scheme (2026-06-16): only stores an EXPLICIT user pick made
// via Settings. The old v1 `wordsnap.lang` cached every auto-detected lang
// indefinitely, which made the mini-app ignore the user's current Telegram
// language preference. tApps Center moderator flagged this on 2026-06-16
// ("Currently app ignores user language preferences set in Telegram
// settings and show up in Ukrainian") — the v2 scheme follows the tApps
// Center requirement: respect the live Telegram `language_code` on every
// load, override only if the user has explicitly chosen otherwise.
const STORAGE_KEY = 'wordsnap.lang.v2';
const EXPLICIT_KEY = 'wordsnap.lang.explicit';

function getInitialLang() {
  // First check whether the user has EXPLICITLY chosen a lang via Settings.
  // We only honour localStorage when it's marked explicit — otherwise it's
  // a stale auto-detection from a past visit that would mask their current
  // Telegram language preference.
  try {
    if (localStorage.getItem(EXPLICIT_KEY) === '1') {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
    }
  } catch {}

  const tg = window.Telegram?.WebApp;
  // tApps Center deeplink (?startapp=tapps[...]) — force EN regardless of
  // moderator's Telegram language. Same as before; this stays the strongest
  // possible signal for the moderator-facing entry point.
  const startParam = tg?.initDataUnsafe?.start_param || '';
  if (typeof startParam === 'string' && (startParam === 'tapps' || startParam.startsWith('tapps_'))) {
    return 'en';
  }

  // Default path — detect from Telegram language_code on every load.
  // tApps Center requirement: "English should be set as the default
  // language and should only switch if your app supports the language
  // detected in the user's Telegram client."
  return detectLang(tg?.initDataUnsafe?.user?.language_code);
}

function persistExplicitLang(lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
    localStorage.setItem(EXPLICIT_KEY, '1');
  } catch {}
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getInitialLang);
  const [loaded, setLoaded] = useState(false);

  // SettingsPage calls setLang — this is the ONLY path that marks the lang
  // explicit. Anywhere else flipping `lang` directly via context value would
  // be wrong; auto-detected langs should not be persisted.
  const setLang = (next) => {
    persistExplicitLang(next);
    setLangState(next);
  };

  // On mount we fetch stats and honour an EXPLICIT native-language choice the
  // user made OUTSIDE this device's mini-app — e.g. they picked Ukrainian in
  // the bot /start flow while their Telegram language is English. The backend
  // flags such picks with `stats.lang_explicit=true` (set only on a real user
  // choice, never on the language auto-detected from `language_code`). When
  // that flag is set we show the app in their chosen `native_lang` even though
  // the phone language differs.
  //
  // This does NOT reintroduce the 2026-06-16 tApps Center bug ("app shows
  // Ukrainian ignoring Telegram language"): that was caused by native_lang
  // defaulting to "uk" for everyone. It's now derived from language_code, and
  // we override the phone language ONLY on an explicit choice. Guards:
  //   - a local in-app explicit pick (EXPLICIT_KEY) always wins — skip;
  //   - the tApps moderator deeplink (?startapp=tapps) forces EN — skip.
  useEffect(() => {
    let cancelled = false;
    const markLoaded = () => { if (!cancelled) setLoaded(true); };

    const applyServerLang = (resp) => {
      if (cancelled) return;
      const data = resp?.data || {};
      let hasLocalExplicit = false;
      try { hasLocalExplicit = localStorage.getItem(EXPLICIT_KEY) === '1'; } catch {}
      const tg = window.Telegram?.WebApp;
      const sp = tg?.initDataUnsafe?.start_param || '';
      const isTapps = typeof sp === 'string' && (sp === 'tapps' || sp.startsWith('tapps_'));
      if (!hasLocalExplicit && !isTapps && data.lang_explicit && SUPPORTED_LANGS.includes(data.native_lang)) {
        setLangState(data.native_lang);
      }
    };
    const onStats = (r) => { applyServerLang(r); markLoaded(); };

    if (getTelegramUserId()) {
      getStats().then(onStats).catch(markLoaded);
    } else {
      let tries = 0;
      const interval = setInterval(() => {
        tries += 1;
        if (getTelegramUserId() || tries >= 10) {
          clearInterval(interval);
          if (getTelegramUserId()) getStats().then(onStats).catch(markLoaded);
          else markLoaded();
        }
      }, 200);
      return () => { cancelled = true; clearInterval(interval); };
    }
    return () => { cancelled = true; };
  }, []);

  const value = useMemo(() => ({ lang, setLang, loaded }), [lang, loaded]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang, loaded } = useLang();
  return {
    lang,
    loaded,
    t: (key, vars) => tFn(key, lang, vars),
    plural: (n, baseKey) => pluralFn(n, lang, baseKey),
  };
}
