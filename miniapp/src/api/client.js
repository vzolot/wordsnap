import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'https://worker-production-abd5.up.railway.app';

const api = axios.create({
  baseURL: API_URL,
});

api.interceptors.request.use((config) => {
  const tg = window.Telegram?.WebApp;
  const userId = tg?.initDataUnsafe?.user?.id;
  if (userId) {
    config.params = { ...config.params, telegram_id: userId };
  }
  return config;
});

export const getWords = () => api.get('/api/words');
export const getStats = () => api.get('/api/stats');
export const getReviewWords = () => api.get('/api/review');
export const submitReview = (wordId, quality) => 
  api.post('/api/review', { word_id: wordId, quality });

export default api;
