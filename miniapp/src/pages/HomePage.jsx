import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, getReviewWords } from '../api/client';

function HomePage() {
  const [stats, setStats] = useState(null);
  const [reviewCount, setReviewCount] = useState(0);
  const navigate = useNavigate();
  const tg = window.Telegram?.WebApp;
  const user = tg?.initDataUnsafe?.user;

  useEffect(() => {
    getStats().then(r => setStats(r.data)).catch(() => {});
    getReviewWords().then(r => setReviewCount(r.data?.length || 0)).catch(() => {});
  }, []);

  return (
    <div className="page">
      <div style={{marginBottom: 24}}>
        <h1 style={{fontSize: 24, fontWeight: 700}}>
          👋 {user?.first_name || 'Привіт'}!
        </h1>
        <p style={{color: 'var(--hint)', marginTop: 4}}>WordSnap — твій словник</p>
      </div>

      {reviewCount > 0 && (
        <div className="card" style={{background: 'rgba(108,99,255,0.2)', border: '1px solid rgba(108,99,255,0.4)', marginBottom: 16}}>
          <p style={{fontWeight: 600}}>🔄 {reviewCount} слів чекають повторення</p>
          <button className="btn" style={{marginTop: 12}} onClick={() => navigate('/review')}>
            Почати повторення
          </button>
        </div>
      )}

      <div className="card">
        <p style={{color: 'var(--hint)', fontSize: 13, marginBottom: 12}}>ПРОГРЕС</p>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
          <div>
            <p style={{fontSize: 28, fontWeight: 700}}>{stats?.total_words || 0}</p>
            <p style={{color: 'var(--hint)', fontSize: 13}}>всього слів</p>
          </div>
          <div>
            <p style={{fontSize: 28, fontWeight: 700}}>{stats?.learned_words || 0}</p>
            <p style={{color: 'var(--hint)', fontSize: 13}}>вивчено</p>
          </div>
        </div>
      </div>

      <button className="btn" style={{marginTop: 8}} onClick={() => navigate('/words')}>
        📚 Мій словник
      </button>
    </div>
  );
}

export default HomePage;
