import { useEffect, useState } from 'react';
import { getWords } from '../api/client';

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
    w.translation?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page">
      <h1 style={{fontSize: 22, fontWeight: 700, marginBottom: 16}}>📚 Мій словник</h1>

      <input
        type="text"
        placeholder="Пошук слова..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{
          width: '100%', padding: '12px 16px', borderRadius: 12,
          background: 'var(--card-bg)', border: '1px solid var(--card-border)',
          color: 'var(--text)', fontSize: 16, marginBottom: 16, outline: 'none'
        }}
      />

      {loading ? (
        <p style={{color: 'var(--hint)', textAlign: 'center'}}>Завантаження...</p>
      ) : filtered.length === 0 ? (
        <p style={{color: 'var(--hint)', textAlign: 'center'}}>Слів не знайдено</p>
      ) : (
        filtered.map(w => (
          <div key={w.id} className="card">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <div>
                <p style={{fontWeight: 600, fontSize: 17}}>{w.word}</p>
                <p style={{color: 'var(--hint)', fontSize: 14, marginTop: 2}}>{w.translation}</p>
              </div>
              <span style={{
                background: 'rgba(108,99,255,0.2)', color: 'var(--accent)',
                padding: '4px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600
              }}>
                lvl {w.repetition || 0}
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default WordsPage;
