// WordSnap Service Worker — мінімалістичний, безпечний.
//
// Стратегія:
//   • /assets/*.{js,css}  — cache-first (Vite хешує імена, тому stale = неможливо)
//   • все інше            — network passthrough (НЕ кешуємо нічого ризикового)
//
// НЕ кешуємо:
//   • index.html  (щоб юзер завжди отримав свіжу версію після нашого деплою)
//   • /api/*      (axios + наш stale-while-revalidate уже керує)
//   • Telegram script, posthog, unsplash — пускаємо як є
//
// Як вимкнути SW локально:
//   1. DevTools → Application → Service Workers → Unregister
//   2. Або поміняй CACHE_NAME — старий кеш сам очиститься на наступному activate

const CACHE_NAME = 'wordsnap-assets-v1';

self.addEventListener('install', (event) => {
  // Не пре-кешуємо нічого — вантажимо on-demand при першому fetch
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // Прибираємо старі версії кешу при оновленні SW
    const names = await caches.keys();
    await Promise.all(
      names.filter((n) => n.startsWith('wordsnap-') && n !== CACHE_NAME)
           .map((n) => caches.delete(n))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Тільки ассети нашого origin'а у /assets/* (хешовані Vite). Інше — passthrough.
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/assets/')) return;
  if (!/\.(js|css|woff2?)$/i.test(url.pathname)) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(req);
    if (cached) return cached;

    try {
      const fresh = await fetch(req);
      // Кешуємо тільки 200 OK, без redirects/errors
      if (fresh && fresh.status === 200 && fresh.type === 'basic') {
        cache.put(req, fresh.clone()).catch(() => {});
      }
      return fresh;
    } catch (e) {
      // Офлайн і нема в кеші — нехай браузер обробить
      return new Response('', { status: 504, statusText: 'Offline' });
    }
  })());
});
