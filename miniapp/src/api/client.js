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
  // Signed Telegram WebApp initData — the backend validates this HMAC and
  // derives telegram_id from it (the query param above is ignored when a
  // valid header is present). Without it the API returns 401. Raw initData
  // lives on Telegram.WebApp.initData.
  const initData = window.Telegram?.WebApp?.initData;
  if (initData) {
    config.headers = config.headers || {};
    config.headers['X-Telegram-Init-Data'] = initData;
  }
  return config;
});

// White-label: бренд/конфіг тенанта (назва, лого, кольори, billing-UI прапор,
// доступність AI-снапу). tenant_id виводиться бекендом з підпису initData —
// клієнт його не передає й не може підмінити.
export const getTenantConfig = () => api.get('/api/tenant/config');
export const getWords = () => api.get('/api/words');
export const getStats = () => api.get('/api/stats');
export const getReviewWords = () => api.get('/api/review');
// Слабкі слова учня — для кнопки «Повторити слабкі слова» з дайджесту (M10).
export const getWeakReviewWords = () => api.get('/api/review/weak');
export const submitReview = (wordId, quality, mode = 'cards') =>
  api.post('/api/review', { word_id: wordId, quality, mode });
export const addWord = (word) => api.post('/api/words', { word });
export const bulkAddWords = (words) => api.post('/api/words/bulk', { words });
// Фото → слова: vision-екстракт кандидатів (потім підтверджуємо через bulk).
export const snapPhoto = (imageB64, imageMime) =>
  api.post('/api/snap/photo', { image_b64: imageB64, image_mime: imageMime });
export const deleteWord = (wordId) => api.delete(`/api/words/${wordId}`);
export const updateWordTranslation = (wordId, translation) =>
  api.patch(`/api/words/${wordId}`, { translation });
export const getSongs = () => api.get('/api/songs');
export const getThemes = () => api.get('/api/themes');
export const createBuyLink = (period = 'monthly') => api.post('/api/buy', null, { params: { period } });
// Telegram Stars (XTR) — secondary payment option. Backend → bot.create_invoice_link →
// returns a tg-invoice URL we feed to `Telegram.WebApp.openInvoice(link, cb)`.
// One-time payment (Stars don't support recurring), so backend marks
// subscription_status="one_time" — scheduler skips re-charge attempts.
export const createStarsInvoice = (period = 'monthly') =>
  api.post('/api/buy/stars', null, { params: { period } });
export const cancelSubscription = () => api.post('/api/cancel_subscription');
export const getReferral = () => api.get('/api/referral');
// Apply a referral on mini-app entry (когда юзер прийшов за `?startapp=ref_<code>`
// прямим лінком замість через чат-бот). Backend сам відхиляє дубль/self-referral.
export const applyReferral = (code) => api.post('/api/apply_referral', { code });

// Persist landing-side ad-cohort survey results when юзер прийшов з реклами
// напряму у mini-app (минаючи бот-чат). Backend парсить composite payload і
// зберігає target_lang/motivation/acquisition_payload. Idempotent.
export const saveSurvey = (payload) =>
  api.post('/api/onboarding/save_survey', { payload });
export const getLeaderboard = () => api.get('/api/leaderboard');
// M16: тижневий груповий лідерборд.
export const getWeeklyLeaderboard = () => api.get('/api/leaderboard/weekly');
export const getTeacherLeaderboard = (groupId = null) =>
  api.get('/api/teacher/leaderboard', { params: groupId ? { group_id: groupId } : {} });
export const updateSettings = (patch) => api.patch('/api/user/settings', patch);

// ── Режим викладача (white-label M5) ──────────────────────────────────────
export const getTeacherDecks = () => api.get('/api/teacher/decks');
export const getTeacherStudents = () => api.get('/api/teacher/students');
export const getTeacherStudentDetail = (id) => api.get(`/api/teacher/students/${id}`);
export const getTeacherDeck = (deckId) => api.get(`/api/teacher/decks/${deckId}`);
export const createTeacherDeck = (payload) => api.post('/api/teacher/decks', payload);
export const updateTeacherDeck = (deckId, patch) =>
  api.patch(`/api/teacher/decks/${deckId}`, patch);
export const deleteTeacherDeck = (deckId) => api.delete(`/api/teacher/decks/${deckId}`);
// M11: фото сторінки → пари «слово–переклад» (превʼю для редагування).
export const createDeckFromPhoto = (imageB64, imageMime) =>
  api.post('/api/teacher/decks/from_photo', { image_b64: imageB64, image_mime: imageMime });
// M13: домашнє завдання з дедлайном.
export const assignHomework = (deckId, dueAtUtc, userIds = null) =>
  api.post(`/api/teacher/decks/${deckId}/homework`, { due_at_utc: dueAtUtc, user_ids: userIds });
export const getHomework = () => api.get('/api/homework');

// M14: режим школи.
export const getSchoolInfo = () => api.get('/api/teacher/school');
export const getTeachers = () => api.get('/api/teacher/teachers');
export const addTeacher = (telegramId) => api.post('/api/teacher/teachers', { telegram_id: telegramId });
export const setTeacherActive = (id, active) => api.post(`/api/teacher/teachers/${id}/active`, { active });
export const getGroups = () => api.get('/api/teacher/groups');
export const createGroup = (name) => api.post('/api/teacher/groups', { name });
export const setGroupMembers = (groupId, userIds) =>
  api.put(`/api/teacher/groups/${groupId}/members`, { user_ids: userIds });

// ── Календар уроків (M9) ──────────────────────────────────────────────────
// Викладач
export const getAvailability = () => api.get('/api/teacher/availability');
export const putAvailability = (slots) => api.put('/api/teacher/availability', { slots });
export const setClosedDate = (day, closed) => api.post('/api/teacher/closed_date', { day, closed });
export const getTeacherLessons = () => api.get('/api/teacher/lessons');
export const teacherCancelLesson = (id) => api.post(`/api/teacher/lessons/${id}/cancel`);
// Ручне бронювання уроку викладачем (довільний час, обходить шаблон доступності).
export const teacherCreateLesson = (studentUserId, startsAtUtc, durationMin = null) =>
  api.post('/api/teacher/lessons', {
    student_user_id: studentUserId, starts_at_utc: startsAtUtc, duration_min: durationMin,
  });
// Учень
export const getCalendarSlots = () => api.get('/api/calendar/slots');
export const getMyLessons = () => api.get('/api/calendar/my');
export const bookLesson = (startsAtUtc) => api.post('/api/calendar/book', { starts_at_utc: startsAtUtc });
export const cancelMyLesson = (id) => api.post(`/api/calendar/lessons/${id}/cancel`);

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

// Bumped on every clearCache so an in-flight prefetch (started before a
// mutation) won't re-write stale data and resurrect a just-deleted/reviewed
// word. prefetchAll() snapshots this and only writes if it hasn't changed.
let _cacheEpoch = 0;

export function clearCache(key) {
  _cacheEpoch += 1;
  try { localStorage.removeItem(`wordsnap.cache.${key}`); } catch {}
}

/**
 * Запускає префетч для головних endpoints — викликається при відкритті
 * додатку, щоб дані вже були готові коли користувач переходить між екранами.
 */
export function prefetchAll() {
  // Snapshot the epoch; if any clearCache fires (a mutation) before a prefetch
  // response lands, drop that write so it can't overwrite freshly-mutated data.
  const epoch = _cacheEpoch;
  const w = (key, data) => { if (_cacheEpoch === epoch) writeCache(key, data); };
  getStats().then(r => w('stats', r.data)).catch(() => {});
  getWords().then(r => w('words', r.data)).catch(() => {});
  getReviewWords().then(r => w('review', r.data)).catch(() => {});
  getSongs().then(r => w('songs', r.data)).catch(() => {});
  getThemes().then(r => w('themes', r.data)).catch(() => {});
  getReferral().then(r => w('referral', r.data)).catch(() => {});
}

export default api;
