import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import NavBar from './components/NavBar';
import DebugBanner from './components/DebugBanner';
import WelcomeStories, { shouldShowWelcome } from './components/WelcomeStories';
import { LangProvider } from './contexts/LangContext';
import { applyReferral, getTelegramUserId, prefetchAll, saveSurvey } from './api/client';
import { initAnalytics, track } from './utils/analytics';
import { getAttribution } from './utils/attribution';
import './App.css';

// Code-split важкі сторінки — кожна підвантажиться лише коли користувач переходить
const WordsPage  = lazy(() => import('./pages/WordsPage'));
const ReviewPage = lazy(() => import('./pages/ReviewPage'));
const StatsPage  = lazy(() => import('./pages/StatsPage'));
const ProPage    = lazy(() => import('./pages/ProPage'));
const SongsPage  = lazy(() => import('./pages/SongsPage'));
const ThemesPage = lazy(() => import('./pages/ThemesPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const LeaderboardPage = lazy(() => import('./pages/LeaderboardPage'));

function applyTheme(scheme) {
  const dark = scheme === 'dark';
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  // Standards/Best Practices: синхронізуємо колір хедера/фону Telegram-чрому
  // з палітрою апи, щоб не було видимого швa між системним bar і нашим body.
  // Значення мають збігатися з `--bg` у `index.css` (light/dark гілки).
  try {
    const tg = window.Telegram?.WebApp;
    const bg = dark ? '#0B0610' : '#FFFFFF';
    tg?.setHeaderColor?.(bg);
    tg?.setBackgroundColor?.(bg);
  } catch { /* old Telegram clients can throw — non-fatal */ }
}

function getInitialTheme() {
  try {
    const saved = localStorage.getItem('wordsnap.theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {}
  const tg = window.Telegram?.WebApp;
  if (tg?.colorScheme) return tg.colorScheme;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const RouteFallback = () => (
  <div className="page"><div className="center-loader"><span className="spinner" /></div></div>
);

function RouteAnalytics() {
  const location = useLocation();
  useEffect(() => {
    try { track('page_viewed', { path: location.pathname }); } catch { /* noop */ }
  }, [location.pathname]);
  return null;
}

// Standards/Best Practices: native Telegram BackButton на підсторінках.
// Показуємо на не-home роутах, ховаємо на home. onClick → history back.
// Замінює in-page «← Back» текстові кнопки у нативний жест.
//
// КРИТИЧНО: коли Telegram відкриває native modal (`tg.openInvoice` для Stars,
// `tg.showPopup`, etc.) — він скидає `BackButton.onClick`. Після закриття
// modal'а кнопка візуально лишається, але вона *мертва* — тап не робить
// нічого. Підхоплюємо подію `invoiceClosed` і перевстановлюємо show + onClick.
function TelegramBackButton() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    const bb = tg?.BackButton;
    if (!bb) return;
    const isHome = location.pathname === '/' || location.pathname === '/home';
    const apply = () => { if (isHome) bb.hide(); else bb.show(); };
    const onBack = () => navigate(-1);

    apply();
    try { bb.onClick(onBack); } catch {}

    // Restore handler after Telegram's native modals close.
    const onModalClosed = () => {
      apply();
      try { bb.onClick(onBack); } catch {}
    };
    try { tg.onEvent?.('invoiceClosed', onModalClosed); } catch {}
    try { tg.onEvent?.('popupClosed', onModalClosed); } catch {}

    return () => {
      try { bb.offClick(onBack); } catch {}
      try { tg.offEvent?.('invoiceClosed', onModalClosed); } catch {}
      try { tg.offEvent?.('popupClosed', onModalClosed); } catch {}
    };
  }, [location.pathname, navigate]);
  return null;
}

function App() {
  const [showWelcome, setShowWelcome] = useState(() => shouldShowWelcome());

  useEffect(() => {
    const replay = () => setShowWelcome(true);
    window.addEventListener('wordsnap:replay-welcome', replay);
    return () => window.removeEventListener('wordsnap:replay-welcome', replay);
  }, []);

  useEffect(() => {
    applyTheme(getInitialTheme());
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      // Standards: запобігаємо випадковому закриттю апи свайпом униз
      // (особливо у вертикальних флоу review/snap), і просимо підтвердження
      // при свідомому закритті — щоб не втратити прогрес.
      try { tg.disableVerticalSwipes?.(); } catch {}
      try { tg.enableClosingConfirmation?.(); } catch {}
      tg.onEvent?.('themeChanged', () => {
        try {
          if (!localStorage.getItem('wordsnap.theme')) applyTheme(tg.colorScheme);
        } catch { applyTheme(tg.colorScheme); }
      });
    } else {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      mq.addEventListener?.('change', e => {
        try {
          if (!localStorage.getItem('wordsnap.theme')) applyTheme(e.matches ? 'dark' : 'light');
        } catch { applyTheme(e.matches ? 'dark' : 'light'); }
      });
    }

    // PostHog ініт + identify за telegram_id (співпадає з distinct_id бекенду).
    // Обгорнено у try/catch щоб збій аналітики не блокував рендер міні-апи.
    const SESS_KEY = 'wordsnap.session.last_active';
    const fireResumed = () => {
      try {
        const prev = parseInt(localStorage.getItem(SESS_KEY) || '0', 10);
        if (prev > 0) {
          const delta = Math.max(0, Math.floor((Date.now() - prev) / 1000));
          track('session_resumed', { since_last_seconds: delta });
        }
      } catch { /* noop */ }
    };
    const stampActive = () => {
      try { localStorage.setItem(SESS_KEY, String(Date.now())); } catch {}
    };

    try {
      const attr = getAttribution();
      // superProps — приклеюються до кожної події (легко сегментувати funnel)
      // personOnceProps — first-touch для cohort'а (НЕ перетирається)
      initAnalytics(getTelegramUserId(), {
        superProps: {
          acquisition_source: attr.acquisition_source,
          acquisition_campaign: attr.acquisition_campaign,
          acquisition_raw: attr.acquisition_raw,
        },
        personOnceProps: {
          acquisition_source: attr.acquisition_source,
          acquisition_campaign: attr.acquisition_campaign,
          acquisition_raw: attr.acquisition_raw,
          acquisition_first_seen_at: attr.acquisition_first_seen_at,
        },
      });
      track('app_opened', {
        last_touch_source: attr.last_touch_source,
        last_touch_campaign: attr.last_touch_campaign,
      });

      // Реферал через direct mini-app лінк (`startapp=ref_<code>`).
      // Перевіряємо last-touch (поточний start_param), не first-touch — інакше
      // applyReferral сипатиме на кожен open у юзера що колись прийшов за
      // ref-лінком. Бекенд все одно idempotent, але без зайвої мережі чистіше.
      if (attr.last_touch_source === 'ref' && attr.last_touch_campaign) {
        applyReferral(attr.last_touch_campaign)
          .then(r => {
            if (r?.data?.applied) {
              track('referral_signup', {
                bonus_days: r.data.bonus_days,
                trial_total_days: r.data.trial_total_days,
                source: 'miniapp_direct',
              });
            }
          })
          .catch(() => { /* noop — мережа/повторний виклик */ });
      }

      // Ad-cohort з landing survey: composite payload (`igads_<camp>_<lang>_<mot>`)
      // прилетає через `startapp`. Шлемо бекенду щоб зберегти target_lang і
      // motivation в БД до того як SPA вирішує показувати welcome-stories.
      const isAdSource = ['igads', 'ig', 'reddit', 'tiktok', 'tt'].includes(attr.last_touch_source);
      if (isAdSource && attr.last_touch_raw) {
        const adPayload = attr.last_touch_raw;
        // Debug-маркер: фіксує що ми взагалі ДІЙШЛИ до виклику. Якщо у
        // PostHog є `app_opened` з ad-source але немає
        // `save_survey_attempted` - це значить новий SPA-бандл не дійшов
        // до юзера (Vercel/Service Worker кеш) і treba force-refresh.
        track('save_survey_attempted', {
          payload_len: adPayload.length,
          source: attr.last_touch_source,
        });
        saveSurvey(adPayload)
          .then(r => {
            const applied = r?.data?.applied || {};
            track('save_survey_succeeded', {
              target_lang: r?.data?.target_lang,
              motivation: r?.data?.motivation,
              applied_fields: Object.keys(applied),
            });
            if (applied.target_lang) {
              try { localStorage.setItem('wordsnap.welcome_seen', '1'); } catch {}
              setShowWelcome(false);
            }
          })
          .catch(err => {
            track('save_survey_failed', {
              status: err?.response?.status || null,
              message: String(err?.message || err).slice(0, 200),
            });
          });
      } else if (isAdSource) {
        track('save_survey_skipped_no_raw', { source: attr.last_touch_source });
      }

      // Перше відкриття цієї сесії — порівнюємо з попередньою (якщо була).
      fireResumed();
      stampActive();
    } catch { /* noop */ }

    // hidden  → запам'ятовуємо момент коли юзер пішов з апи
    // visible → fire session_resumed для повернень всередині однієї вкладки
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') stampActive();
      else if (document.visibilityState === 'visible') {
        fireResumed();
        stampActive();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    // Префетч даних після того як Telegram готовий — Home/Stats/Words рендеряться миттєво
    const prefetchTimer = setTimeout(() => prefetchAll(), 100);

    // Реєструємо Service Worker — кешує тільки /assets/* (immutable hashed
    // chunks). index.html та /api/* проходять без втручання, тому ризику
    // зачекати stale UI на деплоях немає.
    if ('serviceWorker' in navigator && import.meta.env.PROD) {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('[wordsnap] SW register failed:', err?.message);
      });
    }

    // Префетч JS-чанків лазі-сторінок на idle. Перехід по табах стає миттєвим
    // (без waterfall: navigation → fetch chunk → parse → render).
    const idleCb = () => {
      // Порядок — від найімовірніших до рідкісних. Проміси не await'имо —
      // браузер сам кешує модулі, ми просто викликаємо завантаження.
      import('./pages/WordsPage').catch(() => {});
      import('./pages/ReviewPage').catch(() => {});
      import('./pages/StatsPage').catch(() => {});
      import('./pages/SongsPage').catch(() => {});
      import('./pages/ThemesPage').catch(() => {});
      import('./pages/SettingsPage').catch(() => {});
      import('./pages/ProPage').catch(() => {});
      import('./pages/LeaderboardPage').catch(() => {});
    };
    let idleId = 0;
    if ('requestIdleCallback' in window) {
      idleId = window.requestIdleCallback(idleCb, { timeout: 3000 });
    } else {
      idleId = setTimeout(idleCb, 1500);
    }

    return () => {
      clearTimeout(prefetchTimer);
      document.removeEventListener('visibilitychange', onVisibility);
      if (idleId && 'cancelIdleCallback' in window) {
        try { window.cancelIdleCallback(idleId); } catch {}
      } else if (idleId) {
        clearTimeout(idleId);
      }
    };
  }, []);

  return (
    <LangProvider>
      {showWelcome && <WelcomeStories onClose={() => setShowWelcome(false)} />}
      <BrowserRouter>
        <RouteAnalytics />
        <TelegramBackButton />
        <div className="app">
          <DebugBanner />
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/words" element={<WordsPage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/songs" element={<SongsPage />} />
              <Route path="/themes" element={<ThemesPage />} />
              <Route path="/stats" element={<StatsPage />} />
              <Route path="/pro" element={<ProPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/leaderboard" element={<LeaderboardPage />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </Suspense>
          <NavBar />
        </div>
      </BrowserRouter>
    </LangProvider>
  );
}

export default App;
