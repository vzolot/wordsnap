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
export const deleteWord = (wordId) => api.delete(`/api/words/${wordId}`);
export const getSongs = () => api.get('/api/songs');
export const getThemes = () => api.get('/api/themes');
export const createBuyLink = () => api.post('/api/buy');
export const getReferral = () => api.get('/api/referral');

/**
 * Stale-while-revalidate fetch.
 * - Якщо є cached дані не старші TTL — повертає одразу + фоновий refresh
 * - Інакше робить нормальний запит та кешує
 *
 * useCached(key, fetcher, onFresh) — onFresh викликається коли свіжі дані прийшли
 */
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 хв

export function readCache(key, { ignoreTtl = false } = {}) {
  try {
    const raw = localStorage.getItem(`wordsnap.cache.${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.t !== 'number') return null;
    if (!ignoreTtl && Date.now() - parsed.t > CACHE_TTL_MS) return null;
    return parsed.d;
  } catch { return null; }
}

export function writeCache(key, data) {
  try {
    localStorage.setItem(`wordsnap.cache.${key}`, JSON.stringify({ t: Date.now(), d: data }));
  } catch {}
}

export function clearCache(key) {
  try { localStorage.removeItem(`wordsnap.cache.${key}`); } catch {}
}

/**
 * Запускає префетч для головних endpoints — викликається при відкритті
 * додатку, щоб дані вже були готові коли користувач переходить між екранами.
 */
export function prefetchAll() {
  getStats().then(r => writeCache('stats', r.data)).catch(() => {});
  getWords().then(r => writeCache('words', r.data)).catch(() => {});
  getReviewWords().then(r => writeCache('review', r.data)).catch(() => {});
  getSongs().then(r => writeCache('songs', r.data)).catch(() => {});
  getThemes().then(r => writeCache('themes', r.data)).catch(() => {});
  getReferral().then(r => writeCache('referral', r.data)).catch(() => {});
}

export default api;
