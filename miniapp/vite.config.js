import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // @ton/core needs a Node-style `Buffer` global. Vite doesn't polyfill it
  // by default — without these the BOC encoder in `buildCommentPayload`
  // throws `ReferenceError: Buffer is not defined` at render time and
  // crashes the SentryErrorBoundary (saw it 2026-06-09 right after shipping
  // the TON Pay CTA). main.jsx also imports `Buffer` from the polyfill and
  // assigns it onto globalThis to belt-and-braces against any code path
  // that reads `Buffer` before this define is in scope.
  define: {
    global: 'globalThis',
  },
  resolve: {
    alias: {
      buffer: 'buffer/',
    },
  },
  optimizeDeps: {
    include: ['buffer'],
  },
  build: {
    rollupOptions: {
      output: {
        // Виокремлюємо бібліотеки з node_modules у стабільні chunk'и.
        // Хеш змінюється тільки коли реально оновлюється сама бібліотека —
        // на повторних візитах юзер не перезавантажує react/router/axios
        // навіть після нашого деплою.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) {
            return 'vendor-react';
          }
          if (id.includes('/react-router')) return 'vendor-router';
          if (id.includes('/axios/')) return 'vendor-http';
          // Все інше з node_modules — невелика збірна "vendor-misc".
          // posthog-js не сюди — він вантажиться через dynamic import,
          // Vite зробить його окремим chunk'ом автоматично.
          return 'vendor-misc';
        },
      },
    },
  },
})
