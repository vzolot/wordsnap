import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, createBuyLink, getReferral, readCache, writeCache } from '../api/client';
import { track } from '../utils/analytics';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

function ProPage() {
  // Початковий рендер відразу з кешу — Pro card і реферал-блок з'являються
  // одночасно. Свіжі дані фоном.
  const [stats, setStats] = useState(() => readCache('stats', { ignoreTtl: true }));
  const [referral, setReferral] = useState(() => readCache('referral', { ignoreTtl: true }));
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { t } = useT();
  const tg = window.Telegram?.WebApp;

  useEffect(() => {
    track('pro_page_viewed', {
      is_pro: stats?.plan === 'pro',
      is_trial: !!stats?.is_trial,
    });
    getStats().then(r => { setStats(r.data); writeCache('stats', r.data); }).catch(() => {});
    getReferral().then(r => { setReferral(r.data); writeCache('referral', r.data); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCopy = async () => {
    if (!referral?.link) return;
    track('referral_link_copied');
    try {
      await navigator.clipboard.writeText(referral.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch { /* no clipboard API — користувач скопіює вручну з тексту */ }
  };

  const handleShare = () => {
    if (!referral?.link) return;
    track('referral_link_shared');
    const text = t('referral.share_text', { days: referral.bonus_days });
    const url = `https://t.me/share/url?url=${encodeURIComponent(referral.link)}&text=${encodeURIComponent(text)}`;
    if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, '_blank');
  };

  const isPro = stats?.plan === 'pro';
  const [period, setPeriod] = useState('annual'); // дефолт — annual бо вигідніше

  const featureKeys = [
    'pro.features.unlimited',
    'pro.features.ai',
    'pro.features.srs',
    'pro.features.streaks',
    'pro.features.langs',
    'pro.features.export_anki',
  ];

  const handleBuy = async () => {
    track('buy_clicked', { period });
    setLoading(true);
    setError('');
    try {
      const r = await createBuyLink(period);
      const url = r.data?.payment_url;
      if (!url) throw new Error('No payment URL');
      if (tg?.openLink) tg.openLink(url);
      else window.open(url, '_blank');
    } catch (e) {
      track('buy_failed', { period });
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
          {!isPro && (
            <div className="plan-toggle">
              <button
                type="button"
                className={`plan-toggle-btn ${period === 'annual' ? 'active' : ''}`}
                onClick={() => setPeriod('annual')}
              >
                <div className="plan-toggle-label">{t('pro.plan_annual')}</div>
                <div className="plan-toggle-price">$8.99<span>/yr</span></div>
                <div className="plan-toggle-badge">−50%</div>
              </button>
              <button
                type="button"
                className={`plan-toggle-btn ${period === 'monthly' ? 'active' : ''}`}
                onClick={() => setPeriod('monthly')}
              >
                <div className="plan-toggle-label">{t('pro.plan_monthly')}</div>
                <div className="plan-toggle-price">$1.49<span>/mo</span></div>
              </button>
            </div>
          )}

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
              {loading ? t('pro.cta_loading') : t('pro.cta_buy', {
                price: period === 'annual' ? '$8.99' : '$1.49',
              })}
            </button>
          )}
        </div>

        {referral && (
          <div className="referral-card">
            <div className="referral-eyebrow">{t('referral.eyebrow')}</div>
            <div className="referral-title">
              {t('referral.title', { days: referral.bonus_days })}
            </div>
            <div className="referral-sub">{t('referral.sub', { days: referral.bonus_days })}</div>

            <div className="referral-link-row" onClick={handleCopy}>
              <span className="referral-link-text">{referral.link}</span>
              <span className="referral-copy">{copied ? '✓' : '⧉'}</span>
            </div>

            <button className="btn btn-gradient" style={{ marginTop: 10 }} onClick={handleShare}>
              {t('referral.share_cta')}
            </button>

            <div className="referral-stats">
              <div>
                <div className="referral-stat-num">{referral.referrals_count}</div>
                <div className="referral-stat-label">{t('referral.invited')}</div>
              </div>
              <div>
                <div className="referral-stat-num">{(referral.referrals_count || 0) * referral.bonus_days}</div>
                <div className="referral-stat-label">{t('referral.days_earned')}</div>
              </div>
            </div>
          </div>
        )}

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
