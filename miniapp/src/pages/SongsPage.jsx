import { useEffect, useState } from 'react';
import { addWord, getSongs } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import WordResult from '../components/WordResult';

function SongsPage() {
  const [packs, setPacks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const { t } = useT();

  useEffect(() => {
    getSongs().then(r => {
      setPacks(r.data?.packs || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <>
      <AppBar />
      <div className="page">
        {!active ? (
          <SongsList packs={packs} loading={loading} onPick={setActive} t={t} />
        ) : (
          <SongDetail pack={active} onBack={() => setActive(null)} t={t} />
        )}
      </div>
    </>
  );
}

function SongsList({ packs, loading, onPick, t }) {
  if (loading) return <div className="center-loader"><span className="spinner" /></div>;

  return (
    <>
      <h1 className="h1" style={{ marginBottom: 6 }}>🎵 {t('songs.title')}</h1>
      <p className="body-2" style={{ marginBottom: 16 }}>{t('songs.sub')}</p>

      {packs.length === 0 ? (
        <div className="card-soft" style={{ textAlign: 'center', padding: 28 }}>
          <div className="body-2">{t('songs.empty')}</div>
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

function SongDetail({ pack, onBack, t }) {
  const [statusMap, setStatusMap] = useState({}); // word -> 'idle'|'loading'|'added'|'duplicate'|'error'
  const [results, setResults] = useState({}); // word -> data shown inline
  const [errors, setErrors] = useState({}); // word -> error msg

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
    } catch {
      setStatusMap(s => ({ ...s, [word]: 'error' }));
    }
  };

  return (
    <>
      <button className="link-back" onClick={onBack}>{t('songs.back')}</button>

      <div className="song-hero">
        <span className="song-hero-emoji">{pack.emoji}</span>
        <div>
          <h1 className="h1">{pack.title}</h1>
          <p className="body-2">{pack.artist}</p>
        </div>
      </div>
      <p className="body-2" style={{ marginBottom: 14, marginTop: 8 }}>{t('songs.song_sub')}</p>

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
                  <WordResult data={result} />
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

export default SongsPage;
