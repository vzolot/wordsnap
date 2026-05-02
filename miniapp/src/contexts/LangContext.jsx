import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getStats } from '../api/client';
import { detectLang, plural as pluralFn, t as tFn } from '../i18n';

const LangContext = createContext({ lang: 'en', setLang: () => {} });

export function LangProvider({ children }) {
  const initial = (() => {
    const tg = window.Telegram?.WebApp;
    return detectLang(tg?.initDataUnsafe?.user?.language_code);
  })();
  const [lang, setLang] = useState(initial);

  useEffect(() => {
    getStats().then(r => {
      const nl = r.data?.native_lang;
      console.log('[wordsnap] stats native_lang:', nl, 'response:', r.data);
      if (nl) setLang(nl);
    }).catch(err => {
      console.error('[wordsnap] getStats failed:', err?.response?.status, err?.response?.data, err?.message);
    });
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
