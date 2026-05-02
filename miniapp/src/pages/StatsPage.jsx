import { useEffect, useState } from 'react';
import { getStats } from '../api/client';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const { t } = useT();

  useEffect(() => {
    getStats().then(r => {
      setStats(r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;

  const isPro = stats?.plan === 'pro';
  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);

  const tiles = [
    { label: t('stats.total_words'),    value: stats?.total_words || 0,    color: 'violet' },
    { label: t('stats.mastered'),       value: stats?.learned_words || 0,  color: 'lime'   },
    { label: t('stats.learning'),       value: learning,                   color: 'violet' },
    { label: t('stats.reviewed_today'), value: stats?.reviewed_today || 0, color: ''       },
    { label: t('stats.streak_days'),    value: stats?.streak || 0,         color: 'coral'  },
  ];

  return (
    <>
      <AppBar isPro={isPro} />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 14 }}>{t('stats.title')}</h1>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {tiles.map(tile => (
            <div key={tile.label} className="stat-cell" style={{ padding: '18px 16px' }}>
              <div className={`stat-num ${tile.color}`} style={{ fontSize: 28 }}>{tile.value}</div>
              <div className="stat-label">{tile.label}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default StatsPage;
