import { useEffect, useState } from 'react';
import { getStats, readCache, writeCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';
import { replayWelcome } from '../components/WelcomeStories';

function StatsPage() {
  const cached = readCache('stats');
  const [stats, setStats] = useState(cached);
  const [loading, setLoading] = useState(!cached);
  const { t } = useT();

  useEffect(() => {
    getStats().then(r => {
      setStats(r.data);
      writeCache('stats', r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;

  const isPro = stats?.plan === 'pro';
  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);
  const xp = stats?.total_xp || 0;
  const tierXp = stats?.tier_xp ?? 0;
  const tierKey = stats?.tier_key || 'rewards.beginner';
  const nextXp = stats?.next_tier_xp;
  const nextKey = stats?.next_tier_key;
  const nextRewardKey = stats?.next_tier_reward_key;

  const progressPct = (() => {
    if (!nextXp) return 100;
    const span = nextXp - tierXp;
    if (span <= 0) return 100;
    const got = Math.max(0, xp - tierXp);
    return Math.min(100, Math.round((got / span) * 100));
  })();

  const totalSpent = stats?.total_spent || 0;
  const spentLabel = totalSpent > 0 ? `$${totalSpent.toFixed(2)}` : '$0';

  const tiles = [
    { label: t('stats.total_words'),    value: stats?.total_words || 0,    color: 'violet' },
    { label: t('stats.mastered'),       value: stats?.learned_words || 0,  color: 'lime'   },
    { label: t('stats.learning'),       value: learning,                   color: 'violet' },
    { label: t('stats.reviewed_today'), value: stats?.reviewed_today || 0, color: ''       },
    { label: t('stats.streak_days'),    value: stats?.streak || 0,         color: 'coral'  },
    { label: t('stats.total_spent'),    value: spentLabel,                 color: 'pink'   },
  ];

  return (
    <>
      <AppBar isPro={isPro} />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 14 }}>{t('stats.title')}</h1>

        <div className="xp-card">
          <div className="xp-card-head">
            <span>✨ {t('stats.xp_label')}</span>
            <span className="xp-card-tier">{t(tierKey)}</span>
          </div>
          <div className="xp-card-num">{xp}</div>
          <div className="xp-progress">
            <div className="xp-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          {nextKey && nextXp != null ? (
            <div className="xp-card-foot">
              {t('stats.xp_to_next', { n: Math.max(0, nextXp - xp), title: t(nextKey) })}
              {nextRewardKey && (
                <div className="xp-card-reward">🎁 {t('stats.unlocks', { reward: t(nextRewardKey) })}</div>
              )}
            </div>
          ) : (
            <div className="xp-card-foot">{t('stats.tier_max')}</div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {tiles.map(tile => (
            <div key={tile.label} className="stat-cell" style={{ padding: '18px 16px' }}>
              <div className={`stat-num ${tile.color}`} style={{ fontSize: 28 }}>{tile.value}</div>
              <div className="stat-label">{tile.label}</div>
            </div>
          ))}
        </div>

        <button
          className="link-back"
          style={{ marginTop: 22, color: 'var(--text-2)', display: 'block' }}
          onClick={replayWelcome}
        >
          {t('welcome.replay')}
        </button>
      </div>
    </>
  );
}

export default StatsPage;
