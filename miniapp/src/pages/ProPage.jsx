import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, createBuyLink } from '../api/client';
import { track } from '../utils/analytics';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

function ProPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { t } = useT();
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    getStats().then(r => setStats(r.data)).catch(() => {});
  }, []);

  const isPro = stats?.plan === 'pro';

  const featureKeys = [
    'pro.features.unlimited',
    'pro.features.ai',
    'pro.features.srs',
    'pro.features.streaks',
    'pro.features.langs',
  ];

  const handleBuy = async () => {
    track('buy_clicked');
    setLoading(true);
    setError('');
    try {
      const r = await createBuyLink();
      const url = r.data?.payment_url;
      if (!url) throw new Error('No payment URL');
      if (tg?.openLink) tg.openLink(url);
      else window.open(url, '_blank');
    } catch (e) {
      track('buy_failed');
      setError(t('pro.error.payment'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AppBar showProLink={false} />

      <div className="page">
        <span className="pro-eyebrow">{t('pro.eyebrow')}</span>
        <h1 className="pro-headline">
          {t('pro.headline.main')} <span className="gradient-text">{t('pro.headline.accent')}</span>
        </h1>
        <p className="pro-sub">{t('pro.sub')}</p>

        <div className="pro-card">
          <div className="pro-monthly">{t('pro.monthly')}</div>
          <div className="pro-price">
            <span className="pro-price-num">$1.49</span>
            <span className="pro-price-unit">/ month</span>
          </div>

          <ul className="pro-features">
            {featureKeys.map(k => (
              <li key={k} className="pro-feature">
                <span className="check">✓</span>
                <span>{t(k)}</span>
              </li>
            ))}
          </ul>

          {isPro ? (
            <>
              <div style={{ textAlign: 'center', marginTop: 18, padding: '16px 0', background: 'rgba(255,255,255,0.06)', borderRadius: 'var(--r-f)' }}>
                <span style={{ fontWeight: 700 }}>✓ {t('pro.active.heading')}</span>
              </div>
              {stats?.plan_expires_at && (
                <p className="pro-finefoot" style={{ color: 'rgba(255,255,255,0.7)' }}>
                  {t('pro.active.until', { date: new Date(stats.plan_expires_at).toLocaleDateString() })}
                </p>
              )}
            </>
          ) : (
            <button className="pro-cta" onClick={handleBuy} disabled={loading}>
              {loading ? t('pro.cta_loading') : t('pro.cta')}
            </button>
          )}
        </div>

        {!isPro && <p className="pro-finefoot">{t('pro.finefoot')}</p>}
        {error && <p style={{ color: 'var(--coral)', textAlign: 'center', marginTop: 12, fontSize: 13 }}>{error}</p>}

        <button className="btn btn-secondary" style={{ marginTop: 24 }} onClick={() => navigate(-1)}>
          {t('pro.back')}
        </button>
      </div>
    </>
  );
}

export default ProPage;
