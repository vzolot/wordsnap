import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { addWord, bulkAddWords, snapPhoto, clearCache, readCache, writeCache } from '../api/client';
import { pollImage } from '../utils/pollImage';
import { useT } from '../contexts/LangContext';
import { useTenant } from '../contexts/TenantContext';
import { track } from '../utils/analytics';
import WordResult from './WordResult';
import CameraCapture from './CameraCapture';

// File → base64 (без data-URL префіксу) + mime.
function fileToB64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => { const s = String(r.result); resolve({ b64: s.slice(s.indexOf(',') + 1), mime: file.type || 'image/jpeg' }); };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function SnapCard({ nativeLang, targetLang, usedToday, dailyLimit, onAdded }) {
  const { t } = useT();
  const { isDefaultTenant } = useTenant(); // лічильник ліміту — лише WordSnap
  const navigate = useNavigate();
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [errorKind, setErrorKind] = useState(null); // 'limit' | other
  // Фото → слова
  const [camOpen, setCamOpen] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [candidates, setCandidates] = useState(null); // list of words | null
  const [addingBulk, setAddingBulk] = useState(false);
  const [photoMsg, setPhotoMsg] = useState('');
  // Поточне очікуване слово для полінгу картинки. Скидається при reset/submit.
  const activeWordIdRef = useRef(null);
  const unmountedRef = useRef(false);

  useEffect(() => () => { unmountedRef.current = true; }, []);

  const startPoll = (wordId) => {
    pollImage(
      wordId,
      (url) => setResult(prev => (prev ? { ...prev, image_url: url } : prev)),
      () => unmountedRef.current || activeWordIdRef.current !== wordId,
    );
  };

  const submit = async (e) => {
    e?.preventDefault();
    const word = value.trim();
    if (!word || loading) return;
    setLoading(true);
    setError('');
    setErrorKind(null);
    activeWordIdRef.current = null;
    track('add_word_attempted', { length: word.length, source: 'snap_card' });
    try {
      const r = await addWord(word);
      const data = r.data || {};
      if (data.error === 'duplicate') {
        track('add_word_failed', { reason: 'duplicate', source: 'snap_card' });
        setError(t('snap.duplicate')); return;
      }
      if (data.error === 'limit_reached') {
        track('add_word_failed', { reason: 'limit_reached', source: 'snap_card' });
        setError(t('snap.limit'));
        setErrorKind('limit');
        return;
      }
      if (data.error === 'setup_required') {
        track('add_word_failed', { reason: 'setup_required', source: 'snap_card' });
        setError(t('snap.setup_required')); return;
      }
      if (data.error === 'not_real_word') {
        track('add_word_failed', { reason: 'not_real', source: 'snap_card' });
        setError(t('snap.not_real', { word })); return;
      }
      if (!data.ok) {
        track('add_word_failed', { reason: 'unknown', source: 'snap_card' });
        setError(t('snap.error')); return;
      }
      const merged = { ...(data.ai_data || {}), ...(data.word || {}) };
      const wordId = data.word?.id;
      setResult({
        word: merged.word || word,
        translation: merged.translation,
        part_of_speech: merged.part_of_speech,
        difficulty: merged.difficulty,
        examples: merged.examples || [],
        memory_tip: merged.memory_tip,
        image_url: merged.image_url || data.image_url,
      });
      setValue('');
      // Оптимістичне оновлення кешу stats — щоб поки loadAll fetcить свіжі,
      // лічильник 5/10 одразу відбивав нове число (без миготіння на 0).
      const cachedStats = readCache('stats', { ignoreTtl: true });
      if (cachedStats) {
        writeCache('stats', {
          ...cachedStats,
          total_words: (cachedStats.total_words || 0) + 1,
          used_today: (cachedStats.used_today || 0) + 1,
        });
      }
      // Words list однаково треба перетягнути цілком — там новий запис.
      clearCache('words');
      onAdded?.();
      if (wordId) {
        activeWordIdRef.current = wordId;
        startPoll(wordId);
      }
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      const detailStr = typeof detail === 'string'
        ? detail
        : detail ? JSON.stringify(detail) : err?.message || '';
      // Деталі — лише в analytics/console, не в UI: юзер не має бачити сирий
      // backend-payload (напр. FastAPI-валідацію) у повідомленні про помилку.
      track('add_word_failed', { reason: 'network_or_5xx', status: status || 0, detail: detailStr.slice(0, 120), source: 'snap_card' });
      setError(t('snap.error'));
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    activeWordIdRef.current = null;
    setResult(null);
    setError('');
  };

  // ── Фото → слова ──────────────────────────────────────────────────────────
  const doExtract = async (b64, mime) => {
    setError(''); setErrorKind(null); setPhotoMsg(''); setExtracting(true);
    try {
      const r = await snapPhoto(b64, mime);
      if (r.data?.error === 'setup_required') { setError(t('snap.setup_required')); return; }
      const words = r.data?.words || [];
      if (words.length === 0) { setError(t('snap.photo_empty')); return; }
      setCandidates(words);
      track('snap_photo_extracted', { n_words: words.length });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail === 'ai_snap_limit_reached' ? t('snap.photo_limit') : t('snap.error'));
    } finally { setExtracting(false); }
  };

  const onCameraCapture = async (b64, mime) => { setCamOpen(false); await doExtract(b64, mime); };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    const { b64, mime } = await fileToB64(f);
    await doExtract(b64, mime);
  };

  const removeCandidate = (w) => setCandidates((prev) => (prev || []).filter((x) => x !== w));

  const addCandidates = async () => {
    if (!candidates?.length) return;
    setAddingBulk(true); setError('');
    try {
      const r = await bulkAddWords(candidates);
      if (r.data?.error === 'setup_required') { setError(t('snap.setup_required')); return; }
      const added = r.data?.added_count ?? (r.data?.added?.length || 0);
      setPhotoMsg(t('snap.photo_added', { n: added }));
      setCandidates(null);
      // Оптимістично оновлюємо кеш stats + інвалідатимо words (як у submit).
      const cachedStats = readCache('stats', { ignoreTtl: true });
      if (cachedStats) {
        writeCache('stats', {
          ...cachedStats,
          total_words: (cachedStats.total_words || 0) + added,
          used_today: (cachedStats.used_today || 0) + added,
        });
      }
      clearCache('words');
      onAdded?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(detail === 'setup_required' ? t('snap.setup_required') : t('snap.error'));
    } finally { setAddingBulk(false); }
  };

  const photoBusy = extracting || addingBulk;

  return (
    <div className="snap-card">
      <div className="snap-head">
        <span className="snap-title">📸 {t('snap.title')}</span>
        {isDefaultTenant && dailyLimit > 0 && (
          <span className="snap-counter">{t('snap.added_n', { used: usedToday, limit: dailyLimit })}</span>
        )}
      </div>

      {!result ? (
        <form onSubmit={submit}>
          <div className="snap-input-row">
            <div className="snap-input-wrap">
              <input
                className="snap-input"
                type="text"
                value={value}
                onChange={e => { setValue(e.target.value); if (error) { setError(''); setErrorKind(null); } }}
                placeholder={t('snap.placeholder')}
                disabled={loading}
                autoComplete="off"
              />
              {value && !loading && (
                <button
                  type="button"
                  className="snap-input-clear"
                  onClick={() => { setValue(''); setError(''); setErrorKind(null); }}
                  aria-label={t('snap.clear')}
                >
                  ×
                </button>
              )}
            </div>
            <button type="submit" className="snap-submit" disabled={loading || !value.trim()}>
              {loading ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : '✨'}
              <span>{loading ? t('snap.button_loading') : t('snap.button')}</span>
            </button>
          </div>
          {error && (
            <div className="snap-error">
              {error}
              {errorKind === 'limit' && (
                <button
                  type="button"
                  className="btn btn-gradient"
                  style={{ marginTop: 10, width: '100%', padding: '10px', fontSize: 13 }}
                  onClick={() => navigate('/pro')}
                >
                  ✨ {t('snap.buy_pro')}
                </button>
              )}
            </div>
          )}

          <div className="snap-photo-row">
            <button type="button" className="snap-photo-btn"
                    onClick={() => { setError(''); setCamOpen(true); }} disabled={loading || photoBusy}>
              {t('snap.photo')}
            </button>
            <label className={`snap-photo-btn${(loading || photoBusy) ? ' disabled' : ''}`}>
              {t('snap.file')}
              <input type="file" accept="image/*" hidden onChange={onFile} disabled={loading || photoBusy} />
            </label>
          </div>
          {extracting && <p className="snap-photo-msg">{t('snap.extracting')}</p>}
          {photoMsg && <p className="snap-photo-msg ok">{photoMsg}</p>}
          {candidates && candidates.length > 0 && (
            <div className="snap-candidates">
              <p className="snap-cand-hint">{t('snap.found_pick')}</p>
              <div className="snap-chips">
                {candidates.map((w) => (
                  <button key={w} type="button" className="snap-chip" onClick={() => removeCandidate(w)}>
                    {w}<span className="snap-chip-x">×</span>
                  </button>
                ))}
              </div>
              <button type="button" className="snap-submit" style={{ width: '100%', marginTop: 10 }}
                      onClick={addCandidates} disabled={addingBulk}>
                {addingBulk ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : '✨'}
                <span>{t('snap.add_n', { n: candidates.length })}</span>
              </button>
            </div>
          )}
        </form>
      ) : (
        <>
          <WordResult data={result} nativeLang={nativeLang} targetLang={targetLang} />
          <button type="button" className="snap-another" onClick={reset}>
            ✨ {t('snap.another')}
          </button>
        </>
      )}

      {camOpen && (
        <CameraCapture onCapture={onCameraCapture} onClose={() => setCamOpen(false)} busy={extracting} />
      )}
    </div>
  );
}

export default SnapCard;
