// Attribution: визначаємо звідки прийшов юзер для коректної валідації каналів.
//
// Telegram передає startapp param як `tg.initDataUnsafe.start_param`.
// Конвенція тегу — `<source>_<campaign>`, де campaign може мати `_` всередині:
//   igads_val_2605       → source=igads     campaign=val_2605
//   threads_post_42      → source=threads   campaign=post_42
//   referral_<code>      → source=referral  campaign=<code>
//   "" (organic open)    → source=organic   campaign=null
//
// Зберігаємо first-touch у localStorage щоб не залежати від PostHog identify
// race'ів і щоб після reload юзер не "відриався" від кампанії.

const LS_KEY = 'wordsnap.attribution';

function parseStartParam(raw) {
  if (!raw || typeof raw !== 'string') {
    return { source: 'organic', campaign: null, raw: null };
  }
  const idx = raw.indexOf('_');
  if (idx === -1) return { source: raw, campaign: null, raw };
  return { source: raw.slice(0, idx), campaign: raw.slice(idx + 1), raw };
}

export function getAttribution() {
  // 1. Перевіряємо чи вже маємо first-touch у localStorage
  let stored = null;
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) stored = JSON.parse(raw);
  } catch { /* corrupt → ignore */ }

  // 2. Поточний start_param (last-touch — може відрізнятись від first)
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null;
  const currentRaw = tg?.initDataUnsafe?.start_param || null;
  const current = parseStartParam(currentRaw);

  // 3. Якщо first-touch ще нема — фіксуємо поточний (включно з 'organic')
  if (!stored) {
    const firstTouch = {
      source: current.source,
      campaign: current.campaign,
      raw: current.raw,
      first_seen_at: new Date().toISOString(),
    };
    try { localStorage.setItem(LS_KEY, JSON.stringify(firstTouch)); } catch {}
    stored = firstTouch;
  }

  return {
    // First-touch — НЕ перетирається, для cohort-аналізу
    acquisition_source: stored.source,
    acquisition_campaign: stored.campaign,
    acquisition_raw: stored.raw,
    acquisition_first_seen_at: stored.first_seen_at,
    // Last-touch — поточний візит, для debug
    last_touch_source: current.source,
    last_touch_campaign: current.campaign,
  };
}
