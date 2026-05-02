import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getReviewWords, submitReview } from '../api/client';

function ReviewPage() {
  const [words, setWords] = useState([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [stats, setStats] = useState({ reviewed: 0, mastered: 0 });
  const navigate = useNavigate();

  useEffect(() => {
    getReviewWords().then(r => {
      setWords(r.data || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const current = words[index];

  const handleAnswer = async (quality) => {
    await submitReview(current.id, quality).catch(() => {});
    setStats(s => ({
      reviewed: s.reviewed + 1,
      mastered: s.mastered + (quality === 5 ? 1 : 0),
    }));
    if (index + 1 >= words.length) {
      setDone(true);
    } else {
      setIndex(i => i + 1);
      setRevealed(false);
    }
  };

  if (loading) {
    return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;
  }

  if (words.length === 0) {
    return (
      <div className="page">
        <div className="empty-state">
          <div className="empty-illu">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.5">
              <path d="M4 4h12l4 4v12H4z" />
              <line x1="8" y1="11" x2="16" y2="11" />
              <line x1="8" y1="15" x2="14" y2="15" />
            </svg>
          </div>
          <h2 className="empty-title">No words yet</h2>
          <p className="empty-sub">Send a word in the chat to add it to your collection.</p>
          <button className="btn btn-gradient" onClick={() => navigate('/')}>Back to home</button>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page" style={{ textAlign: 'center', paddingTop: 50 }}>
        <div className="success-circle">
          <svg className="success-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12l5 5L20 7" />
          </svg>
        </div>
        <h1 className="h-display" style={{ marginBottom: 8 }}>Session complete!</h1>
        <p className="body-2" style={{ marginBottom: 22, padding: '0 16px' }}>
          You reviewed <b style={{ color: 'var(--text-1)' }}>{stats.reviewed} words</b>{stats.mastered > 0 && <> and mastered <b style={{ color: '#65A30D' }}>{stats.mastered} new ones</b></>}.
        </p>

        <div className="stats-row" style={{ marginBottom: 22 }}>
          <div className="stat-cell">
            <div className="stat-num">{stats.reviewed}</div>
            <div className="stat-label">reviewed</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num violet">+{stats.reviewed * 3} XP</div>
            <div className="stat-label">earned</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num">{stats.mastered}</div>
            <div className="stat-label">mastered</div>
          </div>
        </div>

        <button className="btn btn-primary" onClick={() => navigate('/')}>Back to home</button>
      </div>
    );
  }

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <span className="body-2" style={{ fontWeight: 700, color: 'var(--text-1)' }}>
            {index + 1} / {words.length}
          </span>
          <div className="progress-track" style={{ flex: 1 }}>
            <div className="progress-fill" style={{ width: `${((index) / words.length) * 100}%` }} />
          </div>
        </div>

        <div className="review-card">
          <div className="review-image-placeholder">📸</div>
          <div className="review-pos">{current.part_of_speech || 'word'}</div>
          <div className="review-word">{current.word}</div>

          {!revealed ? (
            <button className="btn-pill" style={{ marginTop: 18 }} onClick={() => setRevealed(true)}>
              Tap to reveal translation
            </button>
          ) : (
            <>
              <div className="review-translation-box">
                <div className="translation-eyebrow">Translation</div>
                <div className="translation-text">{current.translation}</div>
              </div>
              {current.example && (
                <div className="review-examples">
                  <div className="eyebrow" style={{ padding: '0 4px' }}>Example</div>
                  <div className="review-example">"{current.example}"</div>
                </div>
              )}
            </>
          )}
        </div>

        {revealed && (
          <div className="answer-bar">
            <button className="answer-btn forgot" onClick={() => handleAnswer(1)}>
              <span className="icon">✕</span>
              <span>Forgot</span>
            </button>
            <button className="answer-btn hard" onClick={() => handleAnswer(3)}>
              <span className="icon">◐</span>
              <span>Hard</span>
            </button>
            <button className="answer-btn easy" onClick={() => handleAnswer(5)}>
              <span className="icon">✓</span>
              <span>Easy</span>
            </button>
          </div>
        )}
      </div>
    </>
  );
}

export default ReviewPage;
