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
    try {
      initAnalytics(getTelegramUserId());
      track('app_opened');
    } catch { /* noop */ }

    // Префетч даних після того як Telegram готовий — Home/Stats/Words рендеряться миттєво
    const prefetchTimer = setTimeout(() => prefetchAll(), 100);
    return () => clearTimeout(prefetchTimer);
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
