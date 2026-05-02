import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, getReviewWords, getWords } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import SnapCard from '../components/SnapCard';

const greetingKey = () => {
  const h = new Date().getHours();
  if (h < 5)  return 'home.greeting.night';
  if (h < 12) return 'home.greeting.morning';
  if (h < 18) return 'home.greeting.afternoon';
  return 'home.greeting.evening';
};

const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

function badge(word, t) {
  if (word.status === 'mastered') return { cls: 'badge-mastered', text: t('badge.mastered') };
  if ((word.review_count || 0) === 0) return { cls: 'badge-new', text: t('badge.new') };
  return { cls: 'badge-learning', text: t('badge.learning') };
}

function HomePage() {
  const [stats, setStats] = useState(null);
  const [dueCount, setDueCount] = useState(0);
  const [recent, setRecent] = useState([]);
  const navigate = useNavigate();
  const { t, plural } = useT();
  const tg = window.Telegram?.WebApp;
  const userName = tg?.initDataUnsafe?.user?.first_name || '';

  const loadAll = useCallback(() => {
    getStats().then(r => setStats(r.data)).catch(() => {});
    getReviewWords().then(r => setDueCount(r.data?.length || 0)).catch(() => {});
    getWords().then(r => setRecent((r.data || []).slice(0, 3))).catch(() => {});
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const streak = stats?.streak || 0;
  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);
  const mastered = stats?.learned_words || 0;
  const isPro = stats?.plan === 'pro';
  const usedToday = stats?.used_today ?? 0;
  const dailyLimit = stats?.daily_limit ?? (isPro ? 100 : 10);
  const todayIdx = (new Date().getDay() + 6) % 7;

  const dayWord = plural(streak, 'unit.day');
  const wordWord = plural(dueCount, 'unit.word');

  return (
    <>
      <AppBar isPro={isPro} />

      <div className="page">
        <p className="greeting-eyebrow">
          {t(greetingKey())}{userName ? `, ${userName}` : ''}
        </p>
        <h1 className="greeting-title">
          {t('home.ready.before')} <span className="gradient-text">{t('home.ready.accent')}</span>
        </h1>

        <div className="streak-card" style={{ marginTop: 18 }}>
          <div className="streak-eyebrow">🔥 {t('home.streak.label')}</div>
          <div className="streak-days">{streak} {dayWord}</div>
          <div className="streak-sub">
            {dueCount > 0
              ? t('home.streak.due', { n: dueCount, word: wordWord })
              : t('home.streak.nothing')}
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

        <div style={{ marginTop: 14 }}>
          <SnapCard
            nativeLang={stats?.native_lang || 'uk'}
            usedToday={usedToday}
            dailyLimit={dailyLimit}
            onAdded={loadAll}
          />
        </div>

        <div className="stats-row" style={{ marginTop: 14 }}>
          <div className="stat-cell">
            <div className="stat-num violet">{learning}</div>
            <div className="stat-label">{t('home.stat.learning')}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num lime">{mastered}</div>
            <div className="stat-label">{t('home.stat.mastered')}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num coral">{dueCount}</div>
            <div className="stat-label">{t('home.stat.due_now')}</div>
          </div>
        </div>

        <button
          className="cta-review"
          style={{ marginTop: 14, width: '100%' }}
          onClick={() => navigate('/review')}
          disabled={dueCount === 0}
        >
          <span>
            {dueCount > 0
              ? t('home.cta.review', { n: dueCount, word: wordWord })
              : t('home.cta.no_review')}
          </span>
          {dueCount > 0 && <span className="cta-arrow">→</span>}
        </button>

        <div className="section-title">{t('home.recent_snaps')}</div>
        {recent.length === 0 ? (
          <div className="card-soft" style={{ textAlign: 'center', padding: 24 }}>
            <div className="body-2">{t('home.no_words')}</div>
          </div>
        ) : (
          recent.map(w => {
            const b = badge(w, t);
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
