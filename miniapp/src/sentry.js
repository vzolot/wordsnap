import * as Sentry from '@sentry/react';

export function initSentry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;
  try {
    Sentry.init({
      dsn,
      environment: import.meta.env.MODE,
      release: import.meta.env.VITE_RELEASE,
      tracesSampleRate: 0.1,
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: 0,
      // Не шлемо PII
      sendDefaultPii: false,
      ignoreErrors: [
        // Telegram WebApp інколи кидає коли swipes
        'NO_TELEGRAM_ID',
        'ResizeObserver loop',
        'Network Error',
      ],
    });
  } catch (e) {
    // Не валимо застосунок якщо Sentry недоступний
    console.warn('Sentry init failed:', e);
  }
}

// White-label (M8): тег тенанта для сегментації помилок по бренду. Без токенів/PII.
export function setSentryTenant(tenantId, slug) {
  try {
    Sentry.setTag('tenant_id', tenantId);
    if (slug) Sentry.setTag('tenant', slug);
  } catch { /* noop */ }
}

export const SentryErrorBoundary = Sentry.ErrorBoundary;
