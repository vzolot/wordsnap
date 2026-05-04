import { useEffect, useState } from 'react';
import { getWords, readCache, writeCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import SpeakButton from '../components/SpeakButton';

function badge(word, t) {
  if (word.status === 'mastered') return { cls: 'badge-mastered', text: t('badge.mastered') };
  if ((word.review_count || 0) === 0) return { cls: 'badge-new', text: t('badge.new') };
  return { cls: 'badge-learning', text: t('badge.learning') };
}

function WordsPage() {
  const cached = readCache('words');
  const [words, setWords] = useState(Array.isArray(cached) ? cached : []);
  const [loading, setLoading] = useState(!cached);
  const [search, setSearch] = useState('');
  const { t } = useT();

  useEffect(() => {
    getWords().then(r => {
      const list = r.data || [];
      setWords(list);
      writeCache('words', list);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const filtered = words.filter(w =>
    w.word.toLowerCase().includes(search.toLowerCase()) ||
    (w.translation || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <AppBar />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 14 }}>{t('words.title')}</h1>

        <input
          className="input"
          type="text"
          placeholder={t('words.search')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ marginBottom: 14 }}
        />

        {loading ? (
          <div className="center-loader"><span className="spinner" /></div>
        ) : filtered.length === 0 ? (
          <div className="card-soft" style={{ textAlign: 'center', padding: 28 }}>
            <div className="body-2">{words.length === 0 ? t('words.empty') : t('words.no_matches')}</div>
          </div>
        ) : (
          filtered.map(w => {
            const b = badge(w, t);
            return (
              <div key={w.id} className="word-row">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                  <SpeakButton text={w.word} lang={w.target_lang} size="sm" />
                  <div style={{ minWidth: 0 }}>
                    <div className="word-text">{w.word}</div>
                    <div className="word-meta">{w.translation}</div>
                  </div>
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
