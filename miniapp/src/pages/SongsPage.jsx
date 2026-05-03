import { useEffect, useState } from 'react';
import { addWord, getSongs } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

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
          <SongsList
            packs={packs}
            loading={loading}
            onPick={setActive}
            t={t}
          />
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

  const handleAdd = async (word) => {
    if (statusMap[word] === 'loading' || statusMap[word] === 'added') return;
    setStatusMap(s => ({ ...s, [word]: 'loading' }));
    try {
      const r = await addWord(word);
      const data = r.data || {};
      if (data.error === 'duplicate') {
        setStatusMap(s => ({ ...s, [word]: 'duplicate' }));
      } else if (data.ok) {
        setStatusMap(s => ({ ...s, [word]: 'added' }));
      } else {
        setStatusMap(s => ({ ...s, [word]: 'error' }));
      }
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
          return (
            <button
              key={w}
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
          );
        })}
      </div>
    </>
  );
}

export default SongsPage;
