import { useState } from 'react';
import { addWord } from '../api/client';
import { useT } from '../contexts/LangContext';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱' };

function SnapCard({ nativeLang, usedToday, dailyLimit, onAdded }) {
  const { t } = useT();
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e?.preventDefault();
    const word = value.trim();
    if (!word || loading) return;
    setLoading(true);
    setError('');
    try {
      const r = await addWord(word);
      const data = r.data || {};
      if (data.error === 'duplicate') { setError(t('snap.duplicate')); return; }
      if (data.error === 'limit_reached') { setError(t('snap.limit')); return; }
      if (data.error === 'setup_required') { setError(t('snap.setup_required')); return; }
      if (!data.ok) { setError(t('snap.error')); return; }
      setResult({
        word: data.word?.word || word,
        translation: data.word?.translation || data.ai_data?.translation,
        part_of_speech: data.word?.part_of_speech || data.ai_data?.part_of_speech,
        difficulty: data.word?.difficulty || data.ai_data?.difficulty,
        examples: data.word?.examples || data.ai_data?.examples || [],
        memory_tip: data.word?.memory_tip || data.ai_data?.memory_tip,
        image_url: data.word?.image_url || data.image_url,
      });
      setValue('');
      onAdded?.();
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

  const reset = () => { setResult(null); setError(''); };

  const examples = Array.isArray(result?.examples)
    ? result.examples.map(e => typeof e === 'string' ? { sentence: e, explanation: '' } : e)
    : [];

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
          <div className="snap-result-head">
            {result.image_url ? (
              <img src={result.image_url} alt="" className="snap-result-img" />
            ) : (
              <div className="snap-result-img" style={{ display: 'grid', placeItems: 'center', fontSize: 30 }}>📸</div>
            )}
            <div className="snap-result-body">
              <div className="snap-result-meta">
                {result.part_of_speech && <span>{result.part_of_speech}</span>}
                {result.part_of_speech && result.difficulty && <span className="dot">·</span>}
                {result.difficulty && <span>{result.difficulty}</span>}
              </div>
              <div className="snap-result-word">{result.word}</div>
              <div className="snap-result-translation">
                {FLAGS[nativeLang] || '🌐'} {result.translation}
              </div>
            </div>
          </div>

          {examples.length > 0 && (
            <>
              <div className="snap-section-label">{t('snap.examples')}</div>
              {examples.slice(0, 3).map((ex, i) => (
                <div key={i} className="snap-example-item">
                  <span className="snap-example-num">{i + 1}.</span>
                  <span className="snap-example-sentence">{ex.sentence}</span>
                  {ex.explanation && (
                    <span className="snap-example-explanation">→ {ex.explanation}</span>
                  )}
                </div>
              ))}
            </>
          )}

          {result.memory_tip && (
            <div className="snap-tip">
              💡 <span>{result.memory_tip}</span>
            </div>
          )}

          <button type="button" className="snap-another" onClick={reset}>
            ✨ {t('snap.another')}
          </button>
        </>
      )}
    </div>
  );
}

export default SnapCard;
