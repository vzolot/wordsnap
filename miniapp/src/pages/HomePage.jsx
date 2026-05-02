import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, getReviewWords, getWords } from '../api/client';

const greeting = () => {
  const h = new Date().getHours();
  if (h < 5)  return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
};

const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

function statusBadge(word) {
  if (word.repetition >= 3)  return { cls: 'badge-mastered', text: 'Mastered' };
  if (word.repetition >= 1)  return { cls: 'badge-learning', text: 'Learning' };
  return { cls: 'badge-new', text: 'New' };
}

function HomePage() {
  const [stats, setStats] = useState(null);
  const [dueCount, setDueCount] = useState(0);
  const [recent, setRecent] = useState([]);
  const navigate = useNavigate();
  const tg = window.Telegram?.WebApp;
  const userName = tg?.initDataUnsafe?.user?.first_name || 'there';

  useEffect(() => {
    getStats().then(r => setStats(r.data)).catch(() => {});
    getReviewWords().then(r => setDueCount(r.data?.length || 0)).catch(() => {});
    getWords().then(r => setRecent((r.data || []).slice(0, 3))).catch(() => {});
  }, []);

  const streak = stats?.streak || 0;
  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);
  const mastered = stats?.learned_words || 0;
  const todayIdx = (new Date().getDay() + 6) % 7;

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
        <p className="greeting-eyebrow">{greeting()}, {userName}</p>
        <h1 className="greeting-title">
          Ready to <span className="gradient-text">snap a few?</span>
        </h1>

        <div className="streak-card" style={{ marginTop: 18 }}>
          <div className="streak-eyebrow">🔥 Streak</div>
          <div className="streak-days">{streak} {streak === 1 ? 'day' : 'days'}</div>
          <div className="streak-sub">
            {dueCount > 0 ? `Keep going — ${dueCount} word${dueCount === 1 ? '' : 's'} due today` : 'Nothing due today — well done'}
          </div>
          <div className="streak-week">
            {WEEKDAYS.map((d, i) => (
              <div key={i}>
                <div className="streak-day">{d}</div>
                <div className={`streak-bar ${i <= todayIdx && streak > 0 ? 'active' : ''}`} />
              </div>
            ))}
          </div>
        </div>

        <div className="stats-row" style={{ marginTop: 14 }}>
          <div className="stat-cell">
            <div className="stat-num violet">{learning}</div>
            <div className="stat-label">Learning</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num lime">{mastered}</div>
            <div className="stat-label">Mastered</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num coral">{dueCount}</div>
            <div className="stat-label">Due now</div>
          </div>
        </div>

        <button
          className="cta-review"
          style={{ marginTop: 14, width: '100%' }}
          onClick={() => navigate('/review')}
          disabled={dueCount === 0}
        >
          <span>{dueCount > 0 ? `Start review · ${dueCount} word${dueCount === 1 ? '' : 's'}` : 'No words to review'}</span>
          {dueCount > 0 && <span className="cta-arrow">→</span>}
        </button>

        <div className="section-title">Recent snaps</div>
        {recent.length === 0 ? (
          <div className="card-soft" style={{ textAlign: 'center', padding: 24 }}>
            <div className="body-2">No words yet. Send one in the chat to start!</div>
          </div>
        ) : (
          recent.map(w => {
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

export default HomePage;
