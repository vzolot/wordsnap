import { useEffect, useRef, useState } from 'react';
import { addWord, clearCache, readCache, writeCache } from '../api/client';
import { pollImage } from '../utils/pollImage';
import { useT } from '../contexts/LangContext';
import WordResult from './WordResult';

function SnapCard({ nativeLang, targetLang, usedToday, dailyLimit, onAdded }) {
  const { t } = useT();
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
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
    activeWordIdRef.current = null;
    try {
      const r = await addWord(word);
      const data = r.data || {};
      if (data.error === 'duplicate') { setError(t('snap.duplicate')); return; }
      if (data.error === 'limit_reached') { setError(t('snap.limit')); return; }
      if (data.error === 'setup_required') { setError(t('snap.setup_required')); return; }
      if (!data.ok) { setError(t('snap.error')); return; }
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
      setError(`${t('snap.error')} [${status || 'net'}] ${detailStr}`.trim());
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    activeWordIdRef.current = null;
    setResult(null);
    setError('');
  };

  return (
    <div className="snap-card">
      <div className="snap-head">
        <span className="snap-title">📸 {t('snap.title')}</span>
        {dailyLimit > 0 && (
          <span className="snap-counter">{t('snap.added_n', { used: usedToday, limit: dailyLimit })}</span>
        )}
      </div>

      {!result ? (
        <form onSubmit={submit}>
          <div className="snap-input-row">
            <input
              className="snap-input"
              type="text"
              value={value}
              onChange={e => setValue(e.target.value)}
              placeholder={t('snap.placeholder')}
              disabled={loading}
              autoComplete="off"
            />
            <button type="submit" className="snap-submit" disabled={loading || !value.trim()}>
              {loading ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : '✨'}
              <span>{loading ? t('snap.button_loading') : t('snap.button')}</span>
            </button>
          </div>
          {error && <div className="snap-error">{error}</div>}
        </form>
      ) : (
        <>
          <WordResult data={result} nativeLang={nativeLang} targetLang={targetLang} />
          <button type="button" className="snap-another" onClick={reset}>
            ✨ {t('snap.another')}
          </button>
        </>
      )}
    </div>
  );
}

export default SnapCard;
