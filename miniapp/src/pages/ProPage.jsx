import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, createBuyLink, createStarsInvoice, cancelSubscription, getReferral, readCache, writeCache } from '../api/client';
import { track } from '../utils/analytics';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

function ProPageInner() {
  // Початковий рендер відразу з кешу – Pro card і реферал-блок з'являються
  // одночасно. Свіжі дані фоном.
  const [stats, setStats] = useState(() => readCache('stats', { ignoreTtl: true }));
  const [referral, setReferral] = useState(() => readCache('referral', { ignoreTtl: true }));
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelMsg, setCancelMsg] = useState('');
  const [starsLoading, setStarsLoading] = useState(false);
  const [starsMsg, setStarsMsg] = useState('');
  const [starsMsgClass, setStarsMsgClass] = useState('');  // 'ok' | 'err' | ''
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
    } catch { /* no clipboard API – користувач скопіює вручну з тексту */ }
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
  const isCancelled = stats?.subscription_status === 'cancelled';
  const [period, setPeriod] = useState('annual'); // дефолт – annual бо вигідніше

  const handleCancel = async () => {
    track('subscription_cancel_clicked');
    setCancelling(true);
    setCancelMsg('');
    try {
      const r = await cancelSubscription();
      const until = r.data?.pro_until ? new Date(r.data.pro_until).toLocaleDateString() : '';
      setCancelMsg(t('pro.cancel.success', { date: until }));
      setCancelConfirm(false);
      // оновлюємо стан щоб показати cancelled
      getStats().then(rr => { setStats(rr.data); writeCache('stats', rr.data); }).catch(() => {});
      track('subscription_cancelled_ui');
    } catch {
      setCancelMsg(t('pro.cancel.error'));
      track('subscription_cancel_failed');
    } finally {
      setCancelling(false);
    }
  };

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
      track('buy_open_attempt', {
        period,
        opener: tg?.openLink ? 'telegram' : 'window',
      });
      if (tg?.openLink) tg.openLink(url);
      else window.open(url, '_blank');
    } catch {
      track('buy_failed', { period });
      setError(t('pro.error.payment'));
    } finally {
      setLoading(false);
    }
  };

  // Telegram Stars – secondary one-time payment option (no auto-renew). Card
  // (WayForPay) залишається основним (з recurring). Stars відкриваємо через
  // native `tg.openInvoice` – юзер не покидає мініап.
  // Stars-ціни на ~30% вище за USD-номінал картки – щоб після конвертації
  // Telegram (~$0.013/star при withdraw) бот по чистому отримував стільки ж,
  // скільки з картки (~$1.45/міс і ~$8.72/рік net). Бекенд тримає ті ж самі
  // цифри в /api/buy/stars (api_routes.py:create_stars_invoice).
  const STARS_PRICES = { monthly: 129, annual: 799 };

  const handleBuyStars = async () => {
    track('stars_buy_clicked', { period });
    setStarsLoading(true);
    setStarsMsg('');
    setStarsMsgClass('');
    try {
      const r = await createStarsInvoice(period);
      const link = r.data?.invoice_link;
      if (!link) throw new Error('No invoice link');
      if (tg?.openInvoice) {
        // Кнопка лишається disabled, поки відкритий нативний invoice – скидаємо
        // starsLoading у callback'у, не в finally, інакше повторний тап поки
        // модалка відкрита створив би другий інвойс.
        tg.openInvoice(link, (status) => {
          track('stars_invoice_closed', { status, period });
          setStarsLoading(false);
          if (status === 'paid') {
            setStarsMsg(t('pro.stars_success'));
            setStarsMsgClass('ok');
            // Pro має бути активний – перечитуємо stats, щоб UI показав isPro.
            getStats().then(rr => {
              setStats(rr.data);
              writeCache('stats', rr.data);
            }).catch(() => {});
          } else if (status === 'cancelled') {
            setStarsMsg(t('pro.stars_cancelled'));
            setStarsMsgClass('');
          } else {
            // 'failed' | 'pending' | інші – показуємо помилку
            setStarsMsg(t('pro.stars_failed'));
            setStarsMsgClass('err');
          }
        });
      } else {
        // Поза Telegram – нема openInvoice; рідкісний edge-case
        window.open(link, '_blank');
        setStarsLoading(false);
      }
    } catch {
      track('stars_buy_failed', { period });
      setStarsMsg(t('pro.stars_failed'));
      setStarsMsgClass('err');
      setStarsLoading(false);
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

              {/* Скасування підписки – обовʼязкова можливість відписатись */}
              {cancelMsg ? (
                <p className="pro-finefoot" style={{ color: 'rgba(255,255,255,0.7)', marginTop: 12 }}>{cancelMsg}</p>
              ) : isCancelled ? (
                <p className="pro-finefoot" style={{ color: 'rgba(255,255,255,0.55)', marginTop: 12 }}>
                  {t('pro.cancel.already')}
                </p>
              ) : !cancelConfirm ? (
                <button
                  type="button"
                  onClick={() => { setCancelConfirm(true); }}
                  style={{ display: 'block', margin: '14px auto 0', background: 'none', border: 'none',
                    color: 'rgba(255,255,255,0.45)', fontSize: 13, textDecoration: 'underline',
                    textUnderlineOffset: 3, cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  {t('pro.cancel.button')}
                </button>
              ) : (
                <div style={{ marginTop: 14, textAlign: 'center' }}>
                  <p className="pro-finefoot" style={{ color: 'rgba(255,255,255,0.7)', marginBottom: 10 }}>
                    {t('pro.cancel.confirm')}
                  </p>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                    <button type="button" className="btn btn-secondary" style={{ flex: 1, maxWidth: 160 }}
                      onClick={() => setCancelConfirm(false)} disabled={cancelling}>
                      {t('pro.cancel.keep')}
                    </button>
                    <button type="button" className="btn" style={{ flex: 1, maxWidth: 160,
                      background: 'rgba(239,68,68,0.15)', color: '#F87171', border: '1px solid rgba(239,68,68,0.4)' }}
                      onClick={handleCancel} disabled={cancelling}>
                      {cancelling ? '…' : t('pro.cancel.confirm_yes')}
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <button className="pro-cta" onClick={handleBuy} disabled={loading}>
                {loading ? t('pro.cta_loading') : t('pro.cta_buy', {
                  price: period === 'annual' ? '$8.99' : '$1.49',
                })}
              </button>

              {/* Telegram Stars – secondary one-time payment.
                  Card stays primary (with recurring); Stars дає native UX
                  without leaving the mini-app, корисно для аудиторії tApps. */}
              <div className="pro-stars-block">
                <button
                  type="button"
                  className="pro-stars-btn"
                  onClick={handleBuyStars}
                  disabled={starsLoading}
                >
                  {starsLoading
                    ? t('pro.cta_loading')
                    : t('pro.cta_stars', { stars: STARS_PRICES[period] })}
                </button>
                <p className="pro-stars-sub">{t('pro.stars_subtitle')}</p>
                {starsMsg && (
                  <p className={`pro-stars-msg ${starsMsgClass}`}>{starsMsg}</p>
                )}
              </div>
            </>
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

export default ProPageInner;
