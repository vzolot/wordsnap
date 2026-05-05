// PostHog wrapper для міні-апи. No-op якщо VITE_POSTHOG_KEY не встановлений.
// Identify за telegram_id — той самий distinct_id що й бекенд, тому події
// з обох сторін зливаються в одну воронку.
import posthog from 'posthog-js';

const KEY = import.meta.env.VITE_POSTHOG_KEY;
const HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://eu.posthog.com';

let initialized = false;

export function initAnalytics(distinctId) {
  if (!KEY || initialized) return;
  try {
    posthog.init(KEY, {
      api_host: HOST,
      autocapture: false,            // ми вибираємо що трекати, без авто-кліків
      capture_pageview: false,       // SPA — pageview емітимо вручну
      persistence: 'localStorage',
      disable_session_recording: true,
    });
    if (distinctId) posthog.identify(String(distinctId));
    initialized = true;
  } catch (e) {
    // PostHog недоступний — продовжуємо без аналітики
  }
}

export function setDistinctId(distinctId) {
  if (!initialized || !distinctId) return;
  try { posthog.identify(String(distinctId)); } catch {}
}

export function track(event, properties = {}) {
  if (!initialized) return;
  try { posthog.capture(event, properties); } catch {}
}

export function setPersonProps(props) {
  if (!initialized) return;
  try { posthog.setPersonProperties(props); } catch {}
}
