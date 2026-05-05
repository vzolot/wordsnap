// PostHog wrapper для міні-апи. No-op якщо VITE_POSTHOG_KEY не встановлений.
//
// posthog-js НЕ імпортується eагерно — лише через dynamic import коли ключ є.
// Так на iOS Telegram WebView без ключа жодного байта PostHog-бібліотеки не
// вантажиться, і її код не може зламати ініціалізацію міні-апи.

const KEY = import.meta.env.VITE_POSTHOG_KEY;
const HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://eu.posthog.com';

let posthog = null;
let initStarted = false;
let pendingDistinctId = null;
const queue = [];

function flushQueue() {
  if (!posthog) return;
  while (queue.length) {
    const [event, props] = queue.shift();
    try { posthog.capture(event, props); } catch { /* noop */ }
  }
}

export function initAnalytics(distinctId) {
  if (!KEY || initStarted) {
    pendingDistinctId = distinctId || pendingDistinctId;
    return;
  }
  initStarted = true;
  pendingDistinctId = distinctId || pendingDistinctId;

  // Відкладаємо до idle щоб не блокувати перший рендер
  const start = () => {
    import('posthog-js').then(mod => {
      try {
        const ph = mod.default || mod;
        ph.init(KEY, {
          api_host: HOST,
          autocapture: false,
          capture_pageview: false,
          persistence: 'localStorage',
          disable_session_recording: true,
          loaded: () => {
            posthog = ph;
            if (pendingDistinctId) {
              try { ph.identify(String(pendingDistinctId)); } catch {}
            }
            flushQueue();
          },
        });
      } catch { /* noop */ }
    }).catch(() => { /* posthog недоступний */ });
  };

  if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
    window.requestIdleCallback(start, { timeout: 2000 });
  } else {
    setTimeout(start, 0);
  }
}

export function setDistinctId(distinctId) {
  if (!distinctId) return;
  pendingDistinctId = distinctId;
  if (posthog) {
    try { posthog.identify(String(distinctId)); } catch { /* noop */ }
  }
}

export function track(event, properties = {}) {
  if (!KEY) return;
  if (posthog) {
    try { posthog.capture(event, properties); } catch { /* noop */ }
  } else {
    queue.push([event, properties]);
    if (queue.length > 50) queue.shift(); // антиспам
  }
}

export function setPersonProps(props) {
  if (!posthog) return;
  try { posthog.setPersonProperties(props); } catch { /* noop */ }
}
