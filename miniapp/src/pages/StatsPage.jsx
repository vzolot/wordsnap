import { useEffect, useState } from 'react';
import { getStats } from '../api/client';
import AppBar from '../components/AppBar';

function StatsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStats().then(r => {
      setStats(r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;

  const learning = (stats?.total_words || 0) - (stats?.learned_words || 0);

  const tiles = [
    { label: 'Total words',       value: stats?.total_words || 0,    color: 'violet' },
    { label: 'Mastered',          value: stats?.learned_words || 0,  color: 'lime'   },
    { label: 'Learning',          value: learning,                   color: 'violet' },
    { label: 'Reviewed today',    value: stats?.reviewed_today || 0, color: ''       },
    { label: 'Streak days',       value: stats?.streak || 0,         color: 'coral'  },
  ];

  const isPro = stats?.plan === 'pro';

  return (
    <>
      <AppBar isPro={isPro} />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 14 }}>Your progress</h1>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {tiles.map(t => (
            <div key={t.label} className="stat-cell" style={{ padding: '18px 16px' }}>
              <div className={`stat-num ${t.color}`} style={{ fontSize: 28 }}>{t.value}</div>
              <div className="stat-label">{t.label}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default StatsPage;
