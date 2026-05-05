import { useEffect, useRef, useState } from 'react';
import { addWord, clearCache, getThemes, readCache, writeCache } from '../api/client';
import { pollImage } from '../utils/pollImage';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import WordResult from '../components/WordResult';

function ThemesPage() {
  const cached = readCache('themes');
  const [packs, setPacks] = useState(cached?.packs || []);
  const [targetLang, setTargetLang] = useState(cached?.target_lang || null);
  const [loading, setLoading] = useState(!cached);
  const [active, setActive] = useState(null);
  const { t } = useT();

  useEffect(() => {
    getThemes().then(r => {
      setPacks(r.data?.packs || []);
      setTargetLang(r.data?.target_lang || null);
      writeCache('themes', r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <>
      <AppBar />
      <div className="page">
        {!active ? (
          <ThemesList packs={packs} loading={loading} onPick={setActive} t={t} />
        ) : (
          <ThemeDetail pack={active} targetLang={targetLang} onBack={() => setActive(null)} t={t} />
        )}
      </div>
    </>
  );
}

function ThemesList({ packs, loading, onPick, t }) {
  if (loading) return <div className="center-loader"><span className="spinner" /></div>;

  return (
    <>
      <h1 className="h1" style={{ marginBottom: 6 }}>{t('themes.title')}</h1>
      <p className="body-2" style={{ marginBottom: 16 }}>{t('themes.sub')}</p>

      {packs.length === 0 ? (
        <div className="card-soft" style={{ textAlign: 'center', padding: 28 }}>
          <div className="body-2">{t('themes.empty')}</div>
        </div>
      ) : (
        packs.map(p => (
          <button key={p.id} className="song-card" onClick={() => onPick(p)}>
            <span className="song-emoji">{p.emoji}</span>
            <span className="song-info">
              <span className="song-title">{p.title}</span>
              <span className="song-artist">{p.artist}</span>
            </span>
            <span className="song-count">{p.words.length}</span>
          </button>
        ))
      )}
    </>
  );
}

function ThemeDetail({ pack, targetLang, onBack, t }) {
  const [statusMap, setStatusMap] = useState({});
  const [results, setResults] = useState({});
  const [errors, setErrors] = useState({});
  const unmountedRef = useRef(false);
  useEffect(() => () => { unmountedRef.current = true; }, []);

  const handleAdd = async (word) => {
    if (statusMap[word] === 'loading' || statusMap[word] === 'added') return;
    setStatusMap(s => ({ ...s, [word]: 'loading' }));
    setErrors(e => ({ ...e, [word]: undefined }));
    try {
      const r = await addWord(word);
      const data = r.data || {};
      if (data.error === 'duplicate') {
        setStatusMap(s => ({ ...s, [word]: 'duplicate' }));
        setErrors(e => ({ ...e, [word]: t('songs.duplicate') }));
        return;
      }
      if (data.error === 'limit_reached') {
        setStatusMap(s => ({ ...s, [word]: 'error' }));
        setErrors(e => ({ ...e, [word]: data.message || t('songs.empty') }));
        return;
      }
      if (!data.ok) {
        setStatusMap(s => ({ ...s, [word]: 'error' }));
        return;
      }
      const merged = { ...(data.ai_data || {}), ...(data.word || {}) };
      const wordId = data.word?.id;
      setResults(rs => ({
        ...rs,
        [word]: {
          word: merged.word || word,
          translation: merged.translation,
          part_of_speech: merged.part_of_speech,
          difficulty: merged.difficulty,
          examples: merged.examples || [],
          memory_tip: merged.memory_tip,
          image_url: merged.image_url || data.image_url,
        },
      }));
      setStatusMap(s => ({ ...s, [word]: 'added' }));
      const cachedStats = readCache('stats', { ignoreTtl: true });
      if (cachedStats) {
        writeCache('stats', {
          ...cachedStats,
          total_words: (cachedStats.total_words || 0) + 1,
          used_today: (cachedStats.used_today || 0) + 1,
        });
      }
      clearCache('words');
      if (wordId) {
        pollImage(
          wordId,
          (url) => setResults(rs => (
            rs[word] ? { ...rs, [word]: { ...rs[word], image_url: url } } : rs
          )),
          () => unmountedRef.current,
        );
      }
    } catch {
      setStatusMap(s => ({ ...s, [word]: 'error' }));
    }
  };

  return (
    <>
      <button className="link-back" onClick={onBack}>{t('themes.back')}</button>

      <div className="song-hero">
        <span className="song-hero-emoji">{pack.emoji}</span>
        <div>
          <h1 className="h1">{pack.title}</h1>
          <p className="body-2">{pack.artist}</p>
        </div>
      </div>
      <p className="body-2" style={{ marginBottom: 14, marginTop: 8 }}>{t('themes.detail_sub')}</p>

      <div className="song-words">
        {pack.words.map(w => {
          const st = statusMap[w] || 'idle';
          const result = results[w];
          const err = errors[w];
          return (
            <div key={w}>
              <button
                className={`song-word ${st}`}
                onClick={() => handleAdd(w)}
                disabled={st === 'loading' || st === 'added'}
              >
                <span className="song-word-text">{w}</span>
                <span className="song-word-status">
                  {st === 'loading' && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
                  {st === 'added' && '✓'}
                  {st === 'duplicate' && '•'}
                  {st === 'error' && '!'}
                  {st === 'idle' && '+'}
                </span>
              </button>
              {result && st === 'added' && (
                <div className="song-word-result">
                  <WordResult data={result} targetLang={targetLang} />
                </div>
              )}
              {err && st === 'duplicate' && (
                <div className="song-word-hint">{err}</div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

export default ThemesPage;
