import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import HomePage from './pages/HomePage';
import NavBar from './components/NavBar';
import DebugBanner from './components/DebugBanner';
import WelcomeStories, { shouldShowWelcome } from './components/WelcomeStories';
import { LangProvider } from './contexts/LangContext';
import { getTelegramUserId, prefetchAll } from './api/client';
import { initAnalytics, track } from './utils/analytics';
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
  document.documentElement.setAttribute('data-theme', scheme === 'dark' ? 'dark' : 'light');
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
      initAnalytics(getTelegramUserId());
      track('app_opened');
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
