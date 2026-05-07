import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getLeaderboard, readCache, writeCache } from '../api/client';
import { useT } from '../contexts/LangContext';
import { track } from '../utils/analytics';
import AppBar from '../components/AppBar';

const FLAGS = { uk: '🇺🇦', en: '🇬🇧', es: '🇪🇸', pl: '🇵🇱', de: '🇩🇪' };
const MEDALS = ['🥇', '🥈', '🥉'];

function rankDisplay(rank) {
  if (rank <= 3) return MEDALS[rank - 1];
  return `#${rank}`;
}

function LeaderboardPage() {
  const cached = readCache('leaderboard');
  const [data, setData] = useState(cached);
  const [loading, setLoading] = useState(!cached);
  const navigate = useNavigate();
  const { t } = useT();

  useEffect(() => {
    track('leaderboard_viewed');
    getLeaderboard().then(r => {
      setData(r.data);
      writeCache('leaderboard', r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="page"><div className="center-loader"><span className="spinner" /></div></div>;
  }

  if (!data || !data.top?.length) {
    return (
      <>
        <AppBar />
        <div className="page">
          <div className="empty-state">
            <div className="empty-illu">🏆</div>
            <h2 className="empty-title">{t('leaderboard.empty.title')}</h2>
            <p className="empty-sub">{t('leaderboard.empty.sub')}</p>
            <button className="btn btn-gradient" onClick={() => navigate('/')}>{t('common.back')}</button>
          </div>
        </div>
      </>
    );
  }

  const flag = FLAGS[data.target_lang] || '';
  const inTop = data.top.some(r => r.is_self);
  const aboveTop = !inTop && data.self_rank;

  return (
    <>
      <AppBar />

      <div className="page">
        <h1 className="h1" style={{ marginBottom: 4 }}>{t('leaderboard.title')}</h1>
        <p className="body-2" style={{ marginBottom: 18, color: 'var(--text-2)' }}>
          {t('leaderboard.subtitle', { flag })}
        </p>

        {aboveTop && (
          <div className="leaderboard-self-card">
            <div className="leaderboard-self-eyebrow">{t('leaderboard.your_rank')}</div>
            <div className="leaderboard-row self">
              <div className="leaderboard-rank">#{data.self_rank}</div>
              <div className="leaderboard-name">
                {data.self_first_name}
                {data.self_is_pro && <span className="pro-mini">✨</span>}
                <span className="leaderboard-self-tag">{t('leaderboard.you')}</span>
              </div>
              <div className="leaderboard-meta">
                {data.self_streak > 0 && <span className="leaderboard-streak">🔥 {data.self_streak}</span>}
                <span className="leaderboard-xp">{data.self_xp} XP</span>
              </div>
            </div>
          </div>
        )}

        <div className="leaderboard-list">
          {data.top.map(row => (
            <div key={row.rank} className={`leaderboard-row ${row.is_self ? 'self' : ''} ${row.rank <= 3 ? 'top3' : ''}`}>
              <div className="leaderboard-rank">{rankDisplay(row.rank)}</div>
              <div className="leaderboard-name">
                {row.first_name}
                {row.is_pro && <span className="pro-mini">✨</span>}
                {row.is_self && <span className="leaderboard-self-tag">{t('leaderboard.you')}</span>}
              </div>
              <div className="leaderboard-meta">
                {row.streak_days > 0 && <span className="leaderboard-streak">🔥 {row.streak_days}</span>}
                <span className="leaderboard-xp">{row.total_xp} XP</span>
              </div>
            </div>
          ))}
        </div>

        <p className="body-2" style={{ marginTop: 18, color: 'var(--text-2)', fontSize: 12, textAlign: 'center' }}>
          {t('leaderboard.privacy_note')}
        </p>

        <button className="btn btn-secondary" style={{ marginTop: 14 }} onClick={() => navigate(-1)}>
          {t('common.back')}
        </button>
      </div>
    </>
  );
}

export default LeaderboardPage;
