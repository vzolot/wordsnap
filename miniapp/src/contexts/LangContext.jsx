import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getStats, getTelegramUserId } from '../api/client';
import { detectLang, plural as pluralFn, SUPPORTED_LANGS, t as tFn } from '../i18n';

const LangContext = createContext({ lang: 'en', setLang: () => {}, loaded: false });
const STORAGE_KEY = 'wordsnap.lang';

function getInitialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
  } catch {}
  const tg = window.Telegram?.WebApp;
  return detectLang(tg?.initDataUnsafe?.user?.language_code);
}

function persistLang(lang) {
  try { localStorage.setItem(STORAGE_KEY, lang); } catch {}
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getInitialLang);
  const [loaded, setLoaded] = useState(false);

  const setLang = (next) => {
    persistLang(next);
    setLangState(next);
  };

  useEffect(() => {
    let cancelled = false;
    const fetchStats = () => {
      getStats().then(r => {
        if (cancelled) return;
        const nl = r.data?.native_lang;
        if (nl && SUPPORTED_LANGS.includes(nl)) {
          persistLang(nl);
          setLangState(nl);
        }
        setLoaded(true);
      }).catch(err => {
        console.warn('[wordsnap] getStats failed:', err?.message);
        if (!cancelled) setLoaded(true);
      });
    };

    if (getTelegramUserId()) {
      fetchStats();
    } else {
      let tries = 0;
      const interval = setInterval(() => {
        tries += 1;
        if (getTelegramUserId() || tries >= 10) {
          clearInterval(interval);
          if (getTelegramUserId()) fetchStats();
          else if (!cancelled) setLoaded(true);
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
