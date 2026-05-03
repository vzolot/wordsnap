import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clearCache, getReviewWords, submitReview } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪' };

function ReviewPage() {
  const [words, setWords] = useState([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [stats, setStats] = useState({ reviewed: 0, mastered: 0, xp: 0 });
  const [selected, setSelected] = useState(null); // 'forgot' | 'hard' | 'easy'
  const navigate = useNavigate();
  const { t, lang } = useT();

  useEffect(() => {
    getReviewWords().then(r => {
      setWords(r.data || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  // Скидаємо вибір кнопки коли переключаємось на наступне слово
  useEffect(() => {
    setSelected(null);
  }, [index]);

  const current = words[index];

  const handleAnswer = async (quality, key) => {
    if (selected) return;
    setSelected(key);
    await submitReview(current.id, quality).catch(() => {});
    // Інвалідуємо кеш — review/stats тепер застаріли
    clearCache('review');
    clearCache('stats');
    const xpGain = quality === 5 ? 10 : quality === 3 ? 6 : 2;
    setStats(s => ({
      reviewed: s.reviewed + 1,
      mastered: s.mastered + (quality === 5 ? 1 : 0),
      xp: s.xp + xpGain,
    }));
    // Невелика затримка щоб користувач побачив підсвічування вибраної кнопки
    setTimeout(() => {
      if (index + 1 >= words.length) {
        setDone(true);
      } else {
        setIndex(i => i + 1);
        setRevealed(false);
      }
    }, 350);
  };

  if (loading) {
    return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;
  }

  if (words.length === 0) {
    return (
      <>
        <AppBar />
        <div className="page">
          <div className="empty-state">
            <div className="empty-illu">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.5">
                <path d="M4 4h12l4 4v12H4z" />
                <line x1="8" y1="11" x2="16" y2="11" />
                <line x1="8" y1="15" x2="14" y2="15" />
              </svg>
            </div>
            <h2 className="empty-title">{t('review.empty.title')}</h2>
            <p className="empty-sub">{t('review.empty.sub')}</p>
            <button className="btn btn-gradient" onClick={() => navigate('/')}>{t('review.empty.cta')}</button>
          </div>
        </div>
      </>
    );
  }

  if (done) {
    const masteredPart = stats.mastered > 0 ? t('review.complete.mastered_part', { n: stats.mastered }) : '';
    return (
      <>
        <AppBar />
        <div className="page" style={{ textAlign: 'center', paddingTop: 30 }}>
          <div className="success-circle">
            <svg className="success-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12l5 5L20 7" />
            </svg>
          </div>
          <h1 className="h-display" style={{ marginBottom: 8 }}>{t('review.complete.title')}</h1>
          <p className="body-2" style={{ marginBottom: 22, padding: '0 16px' }}>
            {t('review.complete.summary', { reviewed: stats.reviewed, mastered: masteredPart })}
          </p>

          <div className="stats-row" style={{ marginBottom: 22 }}>
            <div className="stat-cell">
              <div className="stat-num">{stats.reviewed}</div>
              <div className="stat-label">{t('review.complete.reviewed')}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-num violet">+{stats.xp} XP</div>
              <div className="stat-label">{t('review.complete.earned')}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-num">{stats.mastered}</div>
              <div className="stat-label">{t('review.complete.mastered')}</div>
            </div>
          </div>

          <button className="btn btn-primary" onClick={() => navigate('/')}>{t('review.back_home')}</button>
        </div>
      </>
    );
  }

  const exampleSentence = (() => {
    const ex = current.examples;
    if (!ex || !ex.length) return null;
    const first = ex[0];
    return typeof first === 'string' ? first : first?.sentence;
  })();

  return (
    <>
      <AppBar />

      <div className="page">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <span className="body-2" style={{ fontWeight: 700, color: 'var(--text-1)' }}>
            {index + 1} / {words.length}
          </span>
          <div className="progress-track" style={{ flex: 1 }}>
            <div className="progress-fill" style={{ width: `${(index / words.length) * 100}%` }} />
          </div>
        </div>

        <div className="review-card">
          {current.image_url ? (
            <img src={current.image_url} alt="" className="review-image" />
          ) : (
            <div className="review-image-placeholder">📸</div>
          )}
          <div className="review-pos">{current.part_of_speech || ''}</div>
          <div className="review-word">{current.word}</div>

          {!revealed ? (
            <button className="btn-pill" style={{ marginTop: 18 }} onClick={() => setRevealed(true)}>
              {t('review.reveal')}
            </button>
          ) : (
            <>
              <div className="review-translation-box">
                <div className="translation-eyebrow">{t('review.translation')}</div>
                <div className="translation-text">{FLAGS[lang] || ''} {current.translation}</div>
                {current.memory_tip && <div className="translation-sub">{current.memory_tip}</div>}
              </div>
              {exampleSentence && (
                <div className="review-examples">
                  <div className="eyebrow" style={{ padding: '0 4px' }}>{t('review.example')}</div>
                  <div className="review-example">"{exampleSentence}"</div>
                </div>
              )}
            </>
          )}
        </div>

        {revealed && (
          <div className={`answer-bar ${selected ? 'locked' : ''}`}>
            <button
              className={`answer-btn forgot ${selected === 'forgot' ? 'selected' : ''}`}
              onClick={() => handleAnswer(1, 'forgot')}
              disabled={!!selected}
            >
              <span className="icon">✕</span>
              <span>{t('review.forgot')}</span>
            </button>
            <button
              className={`answer-btn hard ${selected === 'hard' ? 'selected' : ''}`}
              onClick={() => handleAnswer(3, 'hard')}
              disabled={!!selected}
            >
              <span className="icon">◐</span>
              <span>{t('review.hard')}</span>
            </button>
            <button
              className={`answer-btn easy ${selected === 'easy' ? 'selected' : ''}`}
              onClick={() => handleAnswer(5, 'easy')}
              disabled={!!selected}
            >
              <span className="icon">✓</span>
              <span>{t('review.easy')}</span>
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export default ReviewPage;
