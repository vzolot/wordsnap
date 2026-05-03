import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'https://worker-production-abd5.up.railway.app';

const api = axios.create({
  baseURL: API_URL,
});

export function getTelegramUserId() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return null;

  const direct = tg.initDataUnsafe?.user?.id;
  if (direct) return direct;

  const raw = tg.initData;
  if (raw) {
    try {
      const params = new URLSearchParams(raw);
      const userStr = params.get('user');
      if (userStr) {
        const parsed = JSON.parse(userStr);
        if (parsed?.id) return parsed.id;
      }
    } catch {
      // ignore
    }
  }
  return null;
}

api.interceptors.request.use((config) => {
  const userId = getTelegramUserId();
  if (userId) {
    config.params = { ...config.params, telegram_id: userId };
  } else {
    return Promise.reject(new Error('NO_TELEGRAM_ID'));
  }
  return config;
});

export const getWords = () => api.get('/api/words');
export const getStats = () => api.get('/api/stats');
export const getReviewWords = () => api.get('/api/review');
export const submitReview = (wordId, quality) =>
  api.post('/api/review', { word_id: wordId, quality });
export const addWord = (word) => api.post('/api/words', { word });
export const getSongs = () => api.get('/api/songs');
export const createBuyLink = () => api.post('/api/buy');

export default api;
