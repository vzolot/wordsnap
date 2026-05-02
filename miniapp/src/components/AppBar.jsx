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
        {showProLink && (
          isPro ? (
            <span className="pro-active-badge">✨ PRO</span>
          ) : (
            <Link to="/pro" className="app-bar-pro">✨ Pro</Link>
          )
        )}
      </div>
    </header>
  );
}

export default AppBar;
