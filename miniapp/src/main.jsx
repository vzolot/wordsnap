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
import { TonConnectUIProvider } from '@tonconnect/ui-react'
import './index.css'
import App from './App.jsx'
import { initSentry, SentryErrorBoundary } from './sentry.js'

initSentry();

// TON Connect provider wraps the whole app so any page can read the connected
// wallet via `useTonAddress` / `useTonConnectUI`. Manifest is served by the
// same miniapp deploy (`public/tonconnect-manifest.json`) — must be a public
// HTTPS URL TON wallets can fetch when verifying the connection request.
const TON_MANIFEST_URL = 'https://miniapp-omega-three.vercel.app/tonconnect-manifest.json';

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
      <TonConnectUIProvider manifestUrl={TON_MANIFEST_URL}>
        <App />
      </TonConnectUIProvider>
    </SentryErrorBoundary>
  </StrictMode>,
)
