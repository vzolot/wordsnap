import { useEffect, useState } from 'react';
import { getStats, getWords, readCache, writeCache, clearCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import ExportModal from '../components/ExportModal';
import SpeakButton from '../components/SpeakButton';
import WordDetailModal from '../components/WordDetailModal';
import { track } from '../utils/analytics';

function badge(word, t) {
  if (word.status === 'mastered') return { cls: 'badge-mastered', text: t('badge.mastered') };
  if ((word.review_count || 0) === 0) return { cls: 'badge-new', text: t('badge.new') };
  return { cls: 'badge-learning', text: t('badge.learning') };
}

function statusOf(w) {
  if (w.status === 'mastered') return 'mastered';
  if ((w.review_count || 0) === 0) return 'new';
  return 'learning';
}

function WordsPage() {
  const cached = readCache('words');
  const cachedStats = readCache('stats');
  const [words, setWords] = useState(Array.isArray(cached) ? cached : []);
  const [loading, setLoading] = useState(!cached);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');   // all | new | learning | mastered
  const [sort, setSort] = useState('recent');    // recent | alpha
  const [active, setActive] = useState(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [nativeLang, setNativeLang] = useState(cachedStats?.native_lang || 'uk');
  const isPro = cachedStats?.plan === 'pro';
  const { t } = useT();

  useEffect(() => {
    getWords().then(r => {
      const list = r.data || [];
      setWords(list);
      writeCache('words', list);
      setLoading(false);
    }).catch(() => setLoading(false));
    if (!cachedStats?.native_lang) {
      getStats().then(r => {
        if (r.data?.native_lang) setNativeLang(r.data.native_lang);
      }).catch(() => {});
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = {
    all: words.length,
    new: words.filter(w => statusOf(w) === 'new').length,
    learning: words.filter(w => statusOf(w) === 'learning').length,
    mastered: words.filter(w => statusOf(w) === 'mastered').length,
  };

  const visible = words
    .filter(w => filter === 'all' || statusOf(w) === filter)
    .filter(w =>
      w.word.toLowerCase().includes(search.toLowerCase()) ||
      (w.translation || '').toLowerCase().includes(search.toLowerCase())
    );

  if (sort === 'alpha') {
    visible.sort((a, b) => a.word.localeCompare(b.word));
  }
  // 'recent' — за замовчуванням бекенд повертає сортовано за created_at desc

  const handleDeleted = (deletedId) => {
    setWords(prev => prev.filter(w => w.id !== deletedId));
    clearCache('words');
    clearCache('stats');
    clearCache('review');
    setActive(null);
  };

  return (
    <>
      <AppBar />

      <div className="page">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h1 className="h1">{t('words.title')}</h1>
          {words.length > 0 && (
            <button
              className="btn-pill"
              onClick={() => setExportOpen(true)}
              style={{ padding: '8px 14px', fontSize: 12 }}
            >
              📥 {t('words.export')}
            </button>
          )}
        </div>

        <input
          className="input"
          type="text"
          placeholder={t('words.search')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ marginBottom: 10 }}
        />

        {words.length > 0 && (
          <>
            <div className="words-chips">
              {[
                { k: 'all',      label: t('words.filter.all'),      count: counts.all },
                { k: 'new',      label: t('words.filter.new'),      count: counts.new },
                { k: 'learning', label: t('words.filter.learning'), count: counts.learning },
                { k: 'mastered', label: t('words.filter.mastered'), count: counts.mastered },
              ].map(c => (
                <button
                  key={c.k}
                  className={`words-chip ${filter === c.k ? 'active' : ''}`}
                  onClick={() => setFilter(c.k)}
                  type="button"
                >
                  {c.label}
                  <span className="words-chip-count">{c.count}</span>
                </button>
              ))}
            </div>
            <div className="words-sort">
              <button
                className={`words-sort-btn ${sort === 'recent' ? 'active' : ''}`}
                onClick={() => setSort('recent')}
                type="button"
              >
                {t('words.sort.recent')}
              </button>
              <button
                className={`words-sort-btn ${sort === 'alpha' ? 'active' : ''}`}
                onClick={() => setSort('alpha')}
                type="button"
              >
                {t('words.sort.alpha')}
              </button>
            </div>
          </>
        )}

        {loading ? (
          <div className="center-loader"><span className="spinner" /></div>
        ) : visible.length === 0 ? (
          <div className="card-soft" style={{ textAlign: 'center', padding: 28 }}>
            <div className="body-2">{words.length === 0 ? t('words.empty') : t('words.no_matches')}</div>
          </div>
        ) : (
          visible.map(w => {
            const b = badge(w, t);
            return (
              <div
                key={w.id}
                className="word-row word-row-clickable"
                role="button"
                tabIndex={0}
                onClick={() => { track('word_detail_viewed', { status: w.status }); setActive(w); }}
                onKeyDown={(e) => { if (e.key === 'Enter') { track('word_detail_viewed', { status: w.status }); setActive(w); } }}
              >
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

      <WordDetailModal
        open={!!active}
        word={active}
        onClose={() => setActive(null)}
        onDeleted={handleDeleted}
        nativeLang={nativeLang}
      />
      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        isPro={isPro}
      />
    </>
  );
}

export default WordsPage;
