import { Link } from 'react-router-dom';
import { useT } from '../contexts/LangContext';
import { useTenant } from '../contexts/TenantContext';
import ThemeToggle from './ThemeToggle';
import { readCache } from '../api/client';

// AppBar reads `isPro` from the stats cache by default so every page gets the
// green PRO badge consistently. The five Pages that don't pass `isPro` were
// previously defaulting to `false` and rendering the pink "Get Pro" CTA even
// for paying users (visible bug 2026-06-09: Words / Topics / Songs tabs
// showed the gradient CTA while Home / Stats showed the green badge for the
// same Pro user). Pages can still override with the explicit `isPro` prop
// when they already compute it for their own logic (HomePage / StatsPage).
function AppBar({ showProLink = true, isPro: isProProp = null }) {
  const { t } = useT();
  const { display_name, logo_url, billingEnabled, isDefaultTenant } = useTenant();
  const closeApp = () => { try { window.Telegram?.WebApp?.close?.(); } catch { /* noop */ } };
  const cached = readCache('stats', { ignoreTtl: true });
  const isPro = isProProp !== null ? isProProp : (cached?.plan === 'pro');
  // Логотип: картинка бренду якщо є, інакше перша літера назви (WordSnap → «W»).
  const initial = (display_name || 'W').trim().charAt(0).toUpperCase();
  // Pro-CTA показуємо лише для тенанта з увімкненим білінгом (WordSnap).
  // Для white-label — жодних згадок Pro/цін.
  const showPro = showProLink && billingEnabled;
  return (
    <header className="app-bar">
      <div className="app-bar-logo">
        {logo_url
          ? <img src={logo_url} alt="" className="app-bar-logo-img" />
          : initial}
      </div>
      <div className="app-bar-titles">
        <div className="app-bar-title">{display_name || 'WordSnap'}</div>
        <div className="app-bar-sub">{t('app.subtitle')}</div>
      </div>
      <div className="app-bar-actions">
        <ThemeToggle />
        {/* Явна кнопка «закрити додаток» (white-label). WordSnap (тенант 1)
            лишається без змін — там працює нативне закриття Telegram. */}
        {!isDefaultTenant && (
          <button className="app-bar-settings" onClick={closeApp} aria-label="Закрити додаток">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        )}
        <Link to="/settings" className="app-bar-settings" aria-label={t('settings.title')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </Link>
        {showPro && (
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
