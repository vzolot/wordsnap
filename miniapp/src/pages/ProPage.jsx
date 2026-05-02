import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, createBuyLink } from '../api/client';
import AppBar from '../components/AppBar';

const FEATURES = [
  'Unlimited word snaps from any chat',
  'AI-generated example sentences',
  'Spaced repetition with smart scheduling',
  'Daily streaks + analytics',
  'Multi-language support (UK, EN, ES, PL)',
];

function ProPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    getStats().then(r => setStats(r.data)).catch(() => {});
  }, []);

  const isPro = stats?.plan === 'pro';

  const handleBuy = async () => {
    setLoading(true);
    setError('');
    try {
      const r = await createBuyLink();
      const url = r.data?.payment_url;
      if (!url) throw new Error('No payment URL');
      if (tg?.openLink) {
        tg.openLink(url);
      } else {
        window.open(url, '_blank');
      }
    } catch (e) {
      setError('Couldn\'t open payment. Try /buy in chat.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AppBar showProLink={false} />

      <div className="page">
        <span className="pro-eyebrow">Pro</span>
        <h1 className="pro-headline">
          Snap unlimited <span className="gradient-text">without limits</span>
        </h1>
        <p className="pro-sub">One coffee a month. Forever vocabulary growth.</p>

        <div className="pro-card">
          <div className="pro-monthly">Monthly</div>
          <div className="pro-price">
            <span className="pro-price-num">$1.49</span>
            <span className="pro-price-unit">/ month</span>
          </div>

          <ul className="pro-features">
            {FEATURES.map(f => (
              <li key={f} className="pro-feature">
                <span className="check">✓</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>

          {isPro ? (
            <>
              <div style={{ textAlign: 'center', marginTop: 18, padding: '16px 0', background: 'rgba(255,255,255,0.06)', borderRadius: 'var(--r-f)' }}>
                <span style={{ fontWeight: 700 }}>✓ You're already Pro</span>
              </div>
              {stats?.plan_expires_at && (
                <p className="pro-finefoot" style={{ color: 'rgba(255,255,255,0.7)' }}>
                  Active until {new Date(stats.plan_expires_at).toLocaleDateString()}
                </p>
              )}
            </>
          ) : (
            <button className="pro-cta" onClick={handleBuy} disabled={loading}>
              {loading ? 'Opening payment…' : 'Start 7-day free trial'}
            </button>
          )}
        </div>

        {!isPro && (
          <p className="pro-finefoot">Cancel anytime · No payment until trial ends</p>
        )}

        {error && (
          <p style={{ color: 'var(--coral)', textAlign: 'center', marginTop: 12, fontSize: 13 }}>{error}</p>
        )}

        <button
          className="btn btn-secondary"
          style={{ marginTop: 24 }}
          onClick={() => navigate(-1)}
        >
          Back
        </button>
      </div>
    </>
  );
}

export default ProPage;
