import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { addWord, clearCache, readCache, writeCache } from '../api/client';
import { pollImage } from '../utils/pollImage';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';
import WordResult from './WordResult';

function SnapCard({ nativeLang, targetLang, usedToday, dailyLimit, onAdded }) {
  const { t } = useT();
  const navigate = useNavigate();
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [errorKind, setErrorKind] = useState(null); // 'limit' | other
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
      track('add_word_failed', { reason: 'network_or_5xx', status: status || 0, source: 'snap_card' });
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
