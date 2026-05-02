import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import WordsPage from './pages/WordsPage';
import ReviewPage from './pages/ReviewPage';
import StatsPage from './pages/StatsPage';
import NavBar from './components/NavBar';
import './App.css';

function applyTheme(scheme) {
  document.documentElement.setAttribute('data-theme', scheme === 'dark' ? 'dark' : 'light');
}

function App() {
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      applyTheme(tg.colorScheme || 'light');
      tg.onEvent?.('themeChanged', () => applyTheme(tg.colorScheme));
    } else {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      applyTheme(mq.matches ? 'dark' : 'light');
      mq.addEventListener?.('change', e => applyTheme(e.matches ? 'dark' : 'light'));
    }
  }, []);

  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/words" element={<WordsPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
        <NavBar />
      </div>
    </BrowserRouter>
  );
}

export default App;
