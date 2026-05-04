import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, getReviewWords, getWords, readCache, writeCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import DayCompletionModal from '../components/DayCompletionModal';
import SnapCard from '../components/SnapCard';

const greetingKey = () => {
  const h = new Date().getHours();
  if (h < 5)  return 'home.greeting.night';
  if (h < 12) return 'home.greeting.morning';
  if (h < 18) return 'home.greeting.afternoon';
  return 'home.greeting.evening';
};

function HomePage() {
  // Stale-while-revalidate: одразу рендеримось з cached даних, потім фоном тягнемо свіжі
  const [stats, setStats] = useState(() => readCache('stats'));
  const [dueCount, setDueCount] = useState(() => {
    const cached = readCache('review');
    return Array.isArray(cached) ? cached.length : 0;
  });
  const navigate = useNavigate();
  const { t, plural } = useT();
  const tg = window.Telegram?.WebApp;
  const userName = tg?.initDataUnsafe?.user?.first_name || '';

  const loadAll = useCallback(() => {
    getStats().then(r => {
      setStats(r.data);
      writeCache('stats', r.data);
    }).catch(() => {});
    getReviewWords().then(r => {
      const list = r.data || [];
      setDueCount(list.length);
      writeCache('review', list);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const streak = stats?.streak || 0;
  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);
  const mastered = stats?.learned_words || 0;
  const isPro = stats?.plan === 'pro';
  const usedToday = stats?.used_today ?? 0;
  const dailyLimit = stats?.daily_limit ?? (isPro ? 100 : 10);

  // Day completion: показуємо модалку коли юзер вперше за сьогодні досяг
  // ліміту. localStorage-флаг гарантує що при reload вона не повторюється.
  const [dayModalOpen, setDayModalOpen] = useState(false);
  const [todayWords, setTodayWords] = useState([]);
  const prevUsedRef = useRef(null);

  useEffect(() => {
    if (!stats || dailyLimit <= 0) return;
    const prev = prevUsedRef.current;
    prevUsedRef.current = usedToday;
    if (prev === null) return; // перший рендер після завантаження stats — не тригеримо
    if (prev < dailyLimit && usedToday >= dailyLimit) {
      const today = new Date().toISOString().slice(0, 10);
      const flagKey = `wordsnap.day_completed.${today}`;
      if (!localStorage.getItem(flagKey)) {
        localStorage.setItem(flagKey, '1');
        // Тягнемо саме сьогоднішні слова — getWords сортує за created_at desc
        getWords().then(r => {
          setTodayWords((r.data || []).slice(0, usedToday));
          setDayModalOpen(true);
        }).catch(() => setDayModalOpen(true));
      }
    }
  }, [stats, usedToday, dailyLimit]);

  const dayWord = plural(streak, 'unit.day');
  const wordWord = plural(dueCount, 'unit.word');

  // 7-day streak visualization (4 weeks compact mini-grid)
  const streakCells = Array.from({ length: 21 }, (_, i) => i < streak);

  return (
    <>
      <AppBar isPro={isPro} />

      <div className="page" style={{ paddingTop: 14 }}>
        <p className="greeting-eyebrow">
          {t(greetingKey())}{userName ? `, ${userName}` : ''}
        </p>
        <h1 className="greeting-title">
          {t('home.ready.before')} <span className="gradient-text">{t('home.ready.accent')}</span>
        </h1>

        <div className="streak-card" style={{ marginTop: 12 }}>
          <div className="streak-card-main">
            <div className="streak-eyebrow">🔥 {t('home.streak.label')}</div>
            <div className="streak-days">{streak} {dayWord}</div>
            <div className="streak-sub">
              {dueCount > 0
                ? t('home.streak.due', { n: dueCount, word: wordWord })
                : t('home.streak.nothing')}
            </div>
          </div>
          <div className="streak-week">
            {[0, 1, 2].map(row => (
              <div key={row} className="streak-week-row">
                {[0, 1, 2, 3, 4, 5, 6].map(col => {
                  const i = row * 7 + col;
                  return <div key={col} className={`streak-week-cell ${streakCells[i] ? 'active' : ''}`} />;
                })}
              </div>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 10 }}>
          <SnapCard
            nativeLang={stats?.native_lang || 'uk'}
            targetLang={stats?.target_lang}
            usedToday={usedToday}
            dailyLimit={dailyLimit}
            onAdded={loadAll}
          />
        </div>

        <div className="stats-row" style={{ marginTop: 10 }}>
          <div className="stat-cell">
            <div className="stat-num violet">{learning}</div>
            <div className="stat-label">{t('home.stat.learning')}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num lime">{mastered}</div>
            <div className="stat-label">{t('home.stat.mastered')}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-num gradient">✨ {stats?.total_xp || 0}</div>
            <div className="stat-label">{t('home.stat.xp')}</div>
          </div>
        </div>

        {dueCount > 0 && (
          <button
            className="cta-review"
            style={{ marginTop: 10, width: '100%' }}
            onClick={() => navigate('/review')}
          >
            <span>{t('home.cta.review', { n: dueCount, word: wordWord })}</span>
            <span className="cta-arrow">→</span>
          </button>
        )}
      </div>

      <DayCompletionModal
        open={dayModalOpen}
        onClose={() => setDayModalOpen(false)}
        onOpenReview={() => { setDayModalOpen(false); navigate('/review'); }}
        todayWords={todayWords}
        streak={streak}
        dueCount={dueCount}
        dailyLimit={dailyLimit}
        nativeLang={stats?.native_lang || 'uk'}
      />
    </>
  );
}

export default HomePage;
