import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
          // Everything else from node_modules → vendor-misc.
          // posthog-js не сюди — він вантажиться через dynamic import,
          // Vite зробить його окремим chunk'ом автоматично.
          return 'vendor-misc';
        },
      },
    },
  },
})
