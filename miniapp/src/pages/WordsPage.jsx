import { useEffect, useState } from 'react';
import { getWords } from '../api/client';

function statusBadge(word) {
  if (word.repetition >= 3)  return { cls: 'badge-mastered', text: 'Mastered' };
  if (word.repetition >= 1)  return { cls: 'badge-learning', text: 'Learning' };
  return { cls: 'badge-new', text: 'New' };
}

function WordsPage() {
  const [words, setWords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    getWords().then(r => {
      setWords(r.data || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const filtered = words.filter(w =>
    w.word.toLowerCase().includes(search.toLowerCase()) ||
    (w.translation || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <header className="app-bar">
        <div className="app-bar-logo">W</div>
        <div>
          <div className="app-bar-title">WordSnap</div>
          <div className="app-bar-sub">mini app</div>
        </div>
      </header>

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 14 }}>My words</h1>

        <input
          className="input"
          type="text"
          placeholder="Search words…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ marginBottom: 14 }}
        />

        {loading ? (
          <div className="center-loader"><span className="spinner" /></div>
        ) : filtered.length === 0 ? (
          <div className="card-soft" style={{ textAlign: 'center', padding: 28 }}>
            <div className="body-2">{words.length === 0 ? 'No words yet — add one in the chat.' : 'No matches'}</div>
          </div>
        ) : (
          filtered.map(w => {
            const b = statusBadge(w);
            return (
              <div key={w.id} className="word-row">
                <div>
                  <div className="word-text">{w.word}</div>
                  <div className="word-meta">{w.translation}</div>
                </div>
                <span className={`badge ${b.cls}`}>{b.text}</span>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

export default WordsPage;
