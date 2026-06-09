// Buffer polyfill — MUST be first, before anything that pulls @ton/core.
// @ton/core's BOC encoder uses Node's Buffer at runtime; browsers don't
// provide it. The Vite config's `define: { global: 'globalThis' }` covers
// most paths, this assignment covers the cases where module-eval reads
// `Buffer` directly. Without this, ProPage crashes the ErrorBoundary on
// import (saw it 2026-06-09 right after shipping the TON Pay CTA).
import { Buffer } from 'buffer'
if (typeof globalThis.Buffer === 'undefined') globalThis.Buffer = Buffer

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initSentry, SentryErrorBoundary } from './sentry.js'

initSentry();

// TON Connect provider used to wrap the entire <App /> here — that loaded
// @tonconnect/ui-react + @ton/core (combined ~200 KB gzipped) on every first
// visit, including for users who never opened Pro. 2026-06-09 Phase 3 split:
// moved the provider INTO ProPage so the TON code lives in the ProPage
// lazy chunk and only downloads when the user actually opens the Pro tab.
// Bundle savings: ~115 KB gzipped on first paint.

// Telegram Mini Apps Analytics SDK — обовʼязковий для tApps Center listing.
// Токен видається @DataChief_bot після реєстрації мініапи; зберігаємо у
// `VITE_TG_ANALYTICS_TOKEN` (Vercel project env var). Якщо токена нема
// (dev/preview), init не викликаємо — sdk кидає у промісі помилку, ловимо.
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
