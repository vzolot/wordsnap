import { Link } from 'react-router-dom';
import { useT } from '../contexts/LangContext';
import ThemeToggle from './ThemeToggle';

function AppBar({ showProLink = true, isPro = false }) {
  const { t } = useT();
  return (
    <header className="app-bar">
      <div className="app-bar-logo">W</div>
      <div className="app-bar-titles">
        <div className="app-bar-title">WordSnap</div>
        <div className="app-bar-sub">{t('app.subtitle')}</div>
      </div>
      <div className="app-bar-actions">
        <ThemeToggle />
        <Link to="/settings" className="app-bar-settings" aria-label={t('settings.title')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </Link>
        {showProLink && (
          isPro ? (
            <Link to="/pro" className="pro-active-badge">✨ PRO</Link>
          ) : (
            <Link to="/pro" className="app-bar-pro">✨ Pro</Link>
          )
        )}
      </div>
    </header>
  );
}

export default AppBar;
