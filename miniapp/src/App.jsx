import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import WordsPage from './pages/WordsPage';
import ReviewPage from './pages/ReviewPage';
import StatsPage from './pages/StatsPage';
import ProPage from './pages/ProPage';
import NavBar from './components/NavBar';
import DebugBanner from './components/DebugBanner';
import { LangProvider } from './contexts/LangContext';
import './App.css';

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

function App() {
  useEffect(() => {
    applyTheme(getInitialTheme());
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      tg.onEvent?.('themeChanged', () => {
        // Only auto-follow if user hasn't picked a theme manually
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
  }, []);

  return (
    <LangProvider>
      <BrowserRouter>
        <div className="app">
          <DebugBanner />
          <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/words" element={<WordsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/pro" element={<ProPage />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
          <NavBar />
        </div>
      </BrowserRouter>
    </LangProvider>
  );
}

export default App;
