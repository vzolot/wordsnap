import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Unbounded – заголовковий шрифт сайту, для онбордингу в стилі лендингу.
import '@fontsource/unbounded/latin-700.css'
import '@fontsource/unbounded/latin-800.css'
import '@fontsource/unbounded/cyrillic-700.css'
import '@fontsource/unbounded/cyrillic-800.css'
import './index.css'
import App from './App.jsx'
import { initSentry, SentryErrorBoundary } from './sentry.js'

initSentry();

// Telegram Mini Apps Analytics SDK – обовʼязковий для tApps Center listing.
// Токен видається @DataChief_bot після реєстрації мініапи; зберігаємо у
// `VITE_TG_ANALYTICS_TOKEN` (Vercel project env var). Якщо токена нема
// (dev/preview), init не викликаємо – sdk кидає у промісі помилку, ловимо.
const tgAnalyticsToken = import.meta.env.VITE_TG_ANALYTICS_TOKEN;
if (tgAnalyticsToken) {
  import('@telegram-apps/analytics')
    .then(({ default: analytics }) =>
      analytics.init({
        token: tgAnalyticsToken,
        appName: 'wordsnap',  // має збігатися з ботом @WordSnapBot у DataChief
      })
    )
    .catch((e) => console.warn('[wordsnap] tg analytics init failed:', e?.message));
}

const Fallback = () => (
  <div style={{ padding: 32, textAlign: 'center', color: '#666' }}>
    <h2>Something went wrong</h2>
    <p>Reload the page to continue.</p>
  </div>
);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <SentryErrorBoundary fallback={<Fallback />}>
      <App />
    </SentryErrorBoundary>
  </StrictMode>,
)
