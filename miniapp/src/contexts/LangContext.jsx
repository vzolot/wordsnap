import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getStats, getTelegramUserId } from '../api/client';
import { detectLang, plural as pluralFn, t as tFn } from '../i18n';

const LangContext = createContext({ lang: 'en', setLang: () => {} });

export function LangProvider({ children }) {
  const initial = (() => {
    const tg = window.Telegram?.WebApp;
    return detectLang(tg?.initDataUnsafe?.user?.language_code);
  })();
  const [lang, setLang] = useState(initial);

  useEffect(() => {
    let cancelled = false;
    const fetchStats = () => {
      getStats().then(r => {
        if (cancelled) return;
        const nl = r.data?.native_lang;
        if (nl) setLang(nl);
      }).catch(err => {
        console.warn('[wordsnap] getStats failed:', err?.message);
      });
    };

    if (getTelegramUserId()) {
      fetchStats();
    } else {
      // Telegram WebApp may inject initDataUnsafe slightly later — retry briefly
      let tries = 0;
      const interval = setInterval(() => {
        tries += 1;
        if (getTelegramUserId() || tries >= 10) {
          clearInterval(interval);
          if (getTelegramUserId()) fetchStats();
        }
      }, 200);
      return () => { cancelled = true; clearInterval(interval); };
    }
    return () => { cancelled = true; };
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang } = useLang();
  return {
    lang,
    t: (key, vars) => tFn(key, lang, vars),
    plural: (n, baseKey) => pluralFn(n, lang, baseKey),
  };
}
