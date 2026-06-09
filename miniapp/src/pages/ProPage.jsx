import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStats, createBuyLink, createStarsInvoice, createTonInvoice, getTonPrices, cancelSubscription, getReferral, readCache, writeCache } from '../api/client';
import { TonConnectButton, TonConnectUIProvider, useTonAddress, useTonConnectUI } from '@tonconnect/ui-react';
import { beginCell } from '@ton/core';

// TON manifest lives at the miniapp root, served by Vercel. Was previously
// declared in main.jsx with the provider wrapping the whole app — moved here
// 2026-06-09 Phase 3 so @tonconnect/ui-react + @ton/core ride in this lazy
// chunk instead of the first-paint bundle.
const TON_MANIFEST_URL = 'https://miniapp-omega-three.vercel.app/tonconnect-manifest.json';

// TL-B text-comment payload for a TON transfer: 32-bit op=0 + UTF-8 text.
// Serialised as a single cell, returned as base64 BOC ready for the
// `payload` field of `tonConnectUI.sendTransaction(...)`. Standard pattern
// used by every TON wallet for human-readable transfer memos.
function buildCommentPayload(text) {
  return beginCell()
    .storeUint(0, 32)
    .storeStringTail(text)
    .endCell()
    .toBoc()
    .toString('base64');
}
import { track } from '../utils/analytics';
import { useT } from '../contexts/LangContext';
import AppBar from '../components/AppBar';

function ProPageInner() {
  // Початковий рендер відразу з кешу — Pro card і реферал-блок з'являються
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
  // TON Connect — Phase 1 just wires up the wallet handshake. Phase 2 will
  // add a "Pay X TON" CTA in this same block that constructs a transaction
  // via `tonConnectUI.sendTransaction(...)`.
  const tonAddress = useTonAddress();
  const [tonConnectUI] = useTonConnectUI();
  const [tonLoading, setTonLoading] = useState(false);
  const [tonMsg, setTonMsg] = useState('');
  const [tonMsgClass, setTonMsgClass] = useState('');

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
  const isCancelled = stats?.subscription_status === 'cancelled';
  const [period, setPeriod] = useState('annual'); // дефолт — annual бо вигідніше

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
    } catch (e) {
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
    } catch (e) {
      track('buy_failed', { period });
      setError(t('pro.error.payment'));
    } finally {
      setLoading(false);
    }
  };

  // Telegram Stars — secondary one-time payment option (no auto-renew). Card
  // (WayForPay) залишається основним (з recurring). Stars відкриваємо через
  // native `tg.openInvoice` — юзер не покидає мініап.
  // Stars-ціни на ~30% вище за USD-номінал картки — щоб після конвертації
  // Telegram (~$0.013/star при withdraw) бот по чистому отримував стільки ж,
  // скільки з картки (~$1.45/міс і ~$8.72/рік net). Бекенд тримає ті ж самі
  // цифри в /api/buy/stars (api_routes.py:create_stars_invoice).
  const STARS_PRICES = { monthly: 129, annual: 799 };

  // TON Connect — third payment lane (one-time, no recurring). Frontend
  // builds the TX from the backend-issued `to / amount / comment` triple
  // and asks `tonConnectUI.sendTransaction(...)` to relay it through the
  // user's wallet. Pro activation is server-side via `scheduler/ton_watcher`
  // watching the chain — we poll `getStats` here purely to refresh the UI
  // once the watcher flips the user to Pro.
  // Dynamic TON pricing (Phase 3 — 2026-06-09). Falls back to the static
  // values that were right at $1.70/TON until the API responds.
  const [tonPrices, setTonPrices] = useState({ monthly: 1, annual: 5 });
  useEffect(() => {
    getTonPrices()
      .then(r => {
        const p = r.data?.prices_ton;
        if (p?.monthly && p?.annual) setTonPrices(p);
      })
      .catch(() => { /* keep fallback */ });
  }, []);
  const TON_PRICES = tonPrices;

  const handleBuyTon = async () => {
    track('ton_buy_clicked', { period });
    if (!tonAddress) {
      setTonMsg(t('pro.ton_connect_first'));
      setTonMsgClass('err');
      return;
    }
    setTonLoading(true);
    setTonMsg('');
    setTonMsgClass('');
    try {
      const r = await createTonInvoice(period);
      const { to, amount_nano, comment, valid_until } = r.data;
      await tonConnectUI.sendTransaction({
        validUntil: valid_until,
        messages: [
          {
            address: to,
            amount: amount_nano,
            payload: buildCommentPayload(comment),
          },
        ],
      });
      setTonMsg(t('pro.ton_waiting'));
      setTonMsgClass('');
      track('ton_tx_signed', { period, comment });

      const pollStarted = Date.now();
      const poll = setInterval(async () => {
        try {
          const s = await getStats();
          if (s.data?.plan === 'pro') {
            clearInterval(poll);
            setStats(s.data);
            writeCache('stats', s.data);
            setTonMsg(t('pro.ton_success'));
            setTonMsgClass('ok');
            track('ton_pro_activated', { period });
          } else if (Date.now() - pollStarted > 180_000) {
            clearInterval(poll);
            setTonMsg(t('pro.ton_pending'));
            setTonMsgClass('');
          }
        } catch { /* keep polling */ }
      }, 5000);
    } catch (e) {
      track('ton_buy_failed', { period, err: String(e?.message || e).slice(0, 80) });
      setTonMsg(t('pro.ton_failed'));
      setTonMsgClass('err');
    } finally {
      setTonLoading(false);
    }
  };

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
        tg.openInvoice(link, (status) => {
          track('stars_invoice_closed', { status, period });
          if (status === 'paid') {
            setStarsMsg(t('pro.stars_success'));
            setStarsMsgClass('ok');
            // Pro має бути активний — перечитуємо stats, щоб UI показав isPro.
            getStats().then(rr => {
              setStats(rr.data);
              writeCache('stats', rr.data);
            }).catch(() => {});
          } else if (status === 'cancelled') {
            setStarsMsg(t('pro.stars_cancelled'));
            setStarsMsgClass('');
          } else {
            // 'failed' | 'pending' | інші — показуємо помилку
            setStarsMsg(t('pro.stars_failed'));
            setStarsMsgClass('err');
          }
        });
      } else {
        // Поза Telegram — нема openInvoice; рідкісний edge-case
        window.open(link, '_blank');
      }
    } catch (e) {
      track('stars_buy_failed', { period });
      setStarsMsg(t('pro.stars_failed'));
      setStarsMsgClass('err');
    } finally {
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

              {/* Скасування підписки — обовʼязкова можливість відписатись */}
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

              {/* Telegram Stars — secondary one-time payment.
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

              {/* TON Connect — third payment lane. Phase 1 was the wallet
                  handshake; Phase 2 (this) adds the actual Pay X TON CTA.
                  Server-side `scheduler/ton_watcher` watches TONAPI for the
                  matching comment and activates Pro. */}
              <div className="pro-ton-block">
                <p className="pro-ton-sub">
                  {tonAddress ? t('pro.ton_connected') : t('pro.ton_subtitle')}
                </p>
                <div className="pro-ton-btn-wrap">
                  <TonConnectButton />
                </div>
                {tonAddress && (
                  <>
                    <button
                      type="button"
                      className="pro-stars-btn"
                      style={{ marginTop: 12 }}
                      onClick={handleBuyTon}
                      disabled={tonLoading}
                    >
                      {tonLoading
                        ? t('pro.cta_loading')
                        : t('pro.cta_ton', { amount: TON_PRICES[period] })}
                    </button>
                    <p className="pro-stars-sub" style={{ marginTop: 6 }}>
                      {t('pro.ton_pay_subtitle')}
                    </p>
                  </>
                )}
                {tonMsg && (
                  <p className={`pro-stars-msg ${tonMsgClass}`}>{tonMsg}</p>
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

// Wrapper that mounts the TonConnectUIProvider only for this page (Phase 3
// route-split — kept TON code out of the first-paint bundle). useTonAddress /
// useTonConnectUI inside ProPageInner read from this provider's context.
function ProPage() {
  return (
    <TonConnectUIProvider manifestUrl={TON_MANIFEST_URL}>
      <ProPageInner />
    </TonConnectUIProvider>
  );
}

export default ProPage;
