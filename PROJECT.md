# WordSnap — Project Overview

> Snap a word from any chat → spaced repetition does the rest.
> Telegram Mini App for the Eastern European diaspora learning languages.

**Stack:** FastAPI (Python 3.12) + React 19 (Vite) · Supabase Postgres · Railway + Vercel
**Status:** Production. ~10-day streak users, real payments, Sentry-quiet.
**Last major release:** 2026-05-08 (welcome onboarding + 6 langs + perceived-perf round)
**Bot:** [@WordSnapBot](https://t.me/WordSnapBot) · **Direct mini-app:** https://t.me/WordSnapBot/app · **Web:** https://miniapp-omega-three.vercel.app

---

## 1. What it does

A user adds a word once — by typing it in the bot, picking it from a song lyric, snapping it from a curated theme pack, or via the mini-app input. WordSnap then:

1. Resolves it through GPT-4o-mini → translation, part-of-speech, difficulty, 3 example sentences with usage notes (in target language), memory tip, image keyword.
2. Pulls a matching photo from Unsplash (optimized to 600px / WebP).
3. Schedules SRS reviews using SM-2 (interval grows on `knew`, shrinks on `forgot`). After interval ≥ 21 days the word is **mastered**.
4. Pings the user once per local day at their `reminder_time` with one due word.

Three review modes feed the same SM-2 scheduler:
- **Cards** — flashcard-style flip + 3-button quality (forgot/hard/easy).
- **Quiz** — show word, pick translation among 4 options (3 distractors from user's other words).
- **Spelling** — show translation, type the target-language word (diacritics-insensitive match).

---

## 2. Hosting & stability

| Layer | Provider | Auto-deploy | Notes |
|---|---|---|---|
| Backend (FastAPI + aiogram bot + scheduler) | **Railway** | Yes, on `git push origin main` | One Worker service: API + bot polling + 6 schedulers (reminder, streak-save, recurring-charges, image-backfill, admin-report, **re-engage**) |
| Mini-app (Vite SPA) | **Vercel** | Yes, on `git push origin main` | Project root: `miniapp/`. Service Worker caches hashed assets. |
| Database | **Supabase Postgres** | — | Row-Level Security enabled on all tables; backend connects as superuser, public REST API returns 401. |
| AI | OpenAI `gpt-4o-mini` | — | Backed by `ai_cache` table — 90%+ hit rate after warm-up. ~$0.0005 per cold call. |
| Images | Unsplash API | — | Free tier; requests serialized in image-backfill scheduler. |
| Payments | **WayForPay** | — | Recurring tokens stored in `users.payment_rec_token`. Service URL canonical at `/api/wayforpay/callback`. |
| Errors | **Sentry** | Auto | Backend + frontend. Quiet as of last release. |
| Analytics | **PostHog EU** | — | 30+ events. Dashboard auto-built via `scripts/setup_posthog_dashboard.py`. |

**Stability signals:**
- Auto-migrations run on every Railway boot (`backend/core/auto_migrate.py`) — schema syncs without manual step.
- Each migration in own transaction so a failure doesn't cascade.
- DB-aware `/healthz` endpoint.
- pytest smoke tests + GitHub Actions CI on every push.
- Service Worker caches only hashed assets — `index.html` always fresh, no risk of stale-app after deploy.
- Vendor-split bundle: return visitors re-download just ~24 KB (vs full 365 KB first-load).

**Known carry-over items:**
- Free-tier daily limit is 0 (post-trial blocks adds entirely) — by design, but creates `paywall_hit` spike. Watch the funnel.
- Sentry / PostHog keys must be set in Railway and Vercel envs (already done).

---

## 3. Feature inventory

### 3.1 Telegram bot (entry surface)
- `/start` — onboarding flow (lang → region → demo word card).
- Free-text message in chat → adds the word (same path as mini-app).
- **Photo / screenshot** → gpt-4o-mini vision extracts up to 8 target-language words → inline buttons «➕ word» add them one-tap each.
- **Voice message** → Whisper (auto-detect) transcribes → same extractor on the transcript → same inline-button add UX. Quick transcript preview shown so the user can sanity-check.
- `/buy` — opens Pro purchase link.
- Inline buttons on word reminders ("show translation" / "knew/forgot").
- Streak-save push (one per local day at 22:00) when streak ≥ 3 and zero reviews today.
- Recurring charge scheduler (`scheduler/recurring_charges.py`) — hits WayForPay daily for due tokens.

### 3.2 Mini-app — pages

| Route | Purpose |
|---|---|
| `/` (Home) | Greeting, streak card with calendar dots, snap input, 3 stat tiles |
| `/words` | Searchable word list with status filter chips (all/new/learning/mastered) + sort, click → detail modal |
| `/review` | Three modes via `?mode=cards\|quiz\|spelling`; same SM-2 scheduler |
| `/songs` | Curated lyric packs (Imagine, Yesterday, Perfect…) — tap a song → see word list → add one-by-one or **«Add all»** |
| `/themes` | Curated theme packs (Travel, Food, Office…) — same flow + **«Add all»** |
| `/stats` | XP card with tier ladder, 6 stat tiles, link to `/leaderboard` |
| `/leaderboard` | Top-50 by total XP, segmented by `target_lang`, your-rank pinned if outside top |
| `/pro` | Subscription card (annual/monthly toggle) + referral block |
| `/settings` | Avatar (32 emojis), native lang, target lang, reminders toggle, leaderboard opt-out, timezone |

**Bulk add (2026-05-21):** «Add all» button on Song/Theme detail → `POST /api/words/bulk` (`{words: [...]}`). Respects the snap limit — pre-computes budget (`daily_limit − used`), adds up to it, rest → `skipped_limit` (natural paywall nudge). Dedupes against existing words, generates AI+image with `Semaphore(4)` concurrency, increments counter once for the batch. Returns `{added, duplicates, skipped_limit, failed, added_count, limit_hit}`; UI marks each word ✓/• and shows a summary line (`songs.bulk_*` i18n in 6 langs). Single-word add path unchanged.

### 3.3 Onboarding stories (in-app onboarding)
**Primary onboarding surface** — works for users who arrive via direct mini-app link without ever touching the bot. 4 slides:
1. **Snap mechanic** — hero photo with overlay chips. "Snap a word — that's it."
2. **SRS roadmap** — 5-dot timeline visual (1d → 2d → 4d → 8d → ✓). "Remember it for good."
3. **Native language picker** — 6-button grid, sets `native_lang` in real time.
4. **Target language picker** — 6-button grid, sets `target_lang` and closes.

On completion: `PATCH /api/user/settings` saves both langs, `setLang()` switches UI live, localStorage flag prevents re-show. Pre-filled from cached stats so users who already onboarded via bot just tap through.

All steps tracked in PostHog (`welcome_started`, `welcome_step_viewed{n}`, `welcome_completed`/`welcome_skipped`, plus `lang_selected{role, source: "miniapp_welcome"}` so the same Activation funnel works for direct-link users).

### 3.4 Spaced repetition
- SM-2 algorithm (`backend/core/srs.py`)
- `LEARNING_THRESHOLD = 21` days → `mastered`
- Quality 1/3/5 maps to forgot/struggled/knew → 2/6/10 XP
- Daily push usually picks the most-overdue `learning` word, but with **~8% chance** swaps it for a random `mastered` word as a long-distance check-up (`MASTERED_RESAMPLE_PROBABILITY` in `scheduler/reminder.py`). If the user taps "forgot" on a mastered word, SM-2 auto-demotes it back to `learning` with `interval=1` — mastered is no longer a terminal state.

### 3.5 Word of the Day push
- Scheduler runs every 60s
- Sends one word per local day at user's `reminder_time` (default 09:00 in their `timezone`)
- Anti-spam: `users.last_daily_push_date` (one per local day)
- Stamp date even if no due word so re-checks don't repeat

### 3.5.1 Re-engagement push (added 2026-05-17)
For users who haven't reviewed anything in **7+ days** (`MAX(reviews.reviewed_at) < now - 7d`). One warm pick — preferring their last `forgot`-result word so we surface a real point of friction. Cooldown 30 days per user via `users.last_reengage_push_at` (auto-migrated column). Different message from daily push: this one names the days-since-last-review explicitly and acknowledges the gap ("Давно не бачились"). Lives in `scheduler/reengage.py`; analytics event `reengage_push_sent`.

### 3.6 Pro / monetization

| Plan | Price | Snap limit |
|---|---|---|
| **Trial** (first 7 days) | free | 10 / day |
| **Free** (after trial) | $0 | **3 / rolling 7-day** (freemium tail) |
| **Pro monthly** | $1.49 / mo | 100 / day |
| **Pro annual** | $8.99 / yr | 100 / day |

The free-tier weekly tail (introduced 2026-05-17) replaces the hard 0/day block — keeps the snap habit alive for users who didn't convert in the 7-day trial but might in week 2-4. Counted via `Word.created_at >= now - 7d` (no schema change). Reviews stay unlimited at every tier.

Payment flow: WayForPay HPP via auto-submitted POST form (`/pay` HTML route → `merchantAccount=t_me_218da`). Merchant: WordSnap store `t_me_218da`, active since 2026-04-28; live creds in `wordsnap/.env` (`WAYFORPAY_MERCHANT_*`).

**Recurring subscriptions (reworked 2026-05-20):** uses **WayForPay-managed regular payments** — `create_payment_link` sends `regularOn=1` + `regularMode` (monthly/yearly) + `dateNext` (+30d/+365d). WayForPay charges the first payment immediately and auto-charges each period, POSTing to `/wayforpay/callback` per charge. The callback extends Pro on every new successful payment (idempotent via `is_new_payment` guard — survives WayForPay callback retries). The **self-managed `recurring_charges_loop` cron is disabled** (`bot/main.py`) to avoid double-charging via the saved recToken; its code stays in repo for possible revert to the self-managed model. (`regularOn` is a standard Purchase-API param — no separate cabinet toggle needed; verified the merchant has no dedicated "Регулярні платежі" section and it works via the form.)

**Cancellation (2026-05-21):** mandatory unsubscribe. `POST /api/cancel_subscription` calls WayForPay `regularApi` REMOVE (auth via **merchant password** = `WAYFORPAY_MERCHANT_PASSWORD`, set in `.env` + Railway; NOT the secret key) using `users.subscription_order_ref` (the initial purchase orderReference, stored on first activation, never overwritten by renewals), then sets `auto_renew=False` / `subscription_status='cancelled'` locally. REMOVE reasonCode `4100` (removed) and `4102` ("Rule is not found" — already gone) both count as success. Pro stays active until `plan_expires_at` — no immediate downgrade, no further charges. Local state flips even if the WayForPay call fails (intent honored, failure surfaced). UI: "Cancel subscription" link on ProPage (Pro state) → inline confirm → `pro.cancel.*` i18n in 6 langs. `regularApi` password auth verified live (REMOVE on a dummy ref returned 4102, not an auth error).

**History of payment bugs (all fixed 2026-05-19/20):** (1) Railway env held placeholder merchant creds (`your_merchant_login`) → "Bad Request" on every pay → restored real creds; (2) `WAYFORPAY_WEBHOOK_URL` pointed at `/wayforpay/callback` but route only existed at `/api/wayforpay/callback` → callback 404, Pro never activated → added path alias; (3) `/api/buy` returned `http://` behind Railway proxy → forced https. Verified end-to-end with a live $1.49 test payment (payment_history #5 Approved → Pro re-activated).

**Referrals:** Each user has a unique link. Shareable link generated by `/api/referral` now points at `t.me/<bot>/app?startapp=ref_<code>` — direct mini-app entry, one tap, no intermediate bot chat. The mini-app picks up `start_param`, calls `POST /api/apply_referral` with the code, and the inviter gets a Telegram notification. Old `?start=ref_<code>` links still work via the bot's `/start` handler. Both inviter and invitee get **+10 days Pro** stacked on top of trial → effective 17-day trial for referrals. Tracked via `referral_signup` / `referral_completed`.

### 3.6.1 Affiliate / influencer revenue-share program

Added 2026-05-19. Separate channel from user-to-user referrals — for paid influencer partnerships (Rue, Sheku, and future).

**Mechanics (default Rue terms):**
- Influencer gets a unique `slug` (e.g. `rue`) → trackable **bot-chat** deeplink `https://t.me/WordSnapBot?start=aff_<slug>`.
- **Bot-chat, not direct mini-app (reworked 2026-05-22).** The link opens the bot chat (`?start=`), not the mini-app (`?startapp=`). Reasons: (1) affiliate audiences are international (e.g. Rue's & Sheku's South-African followers don't speak Ukrainian) — the bot onboarding lets them pick their native language first, then launches the mini-app already localized; (2) the mini-app never parsed the `aff_` start_param, so affiliate attribution happens **only** in the bot's `cmd_start` via `apply_affiliate_to_user` — the old `?startapp=aff_` link wasn't crediting the influencer at all. **Affiliate-cohort onboarding is in English** (`onboard.welcome` + `setup.ask_native` forced to `en`); once the user taps a native-language button the rest of the flow continues in that chosen language, and the mini-app opens localized off `users.native_lang`.
- New user taps the link → `users.affiliate_slug` + `users.affiliate_at` set on **first touch only** (never overwritten by subsequent ad clicks or other links).
- Every successful payment by that user within `duration_days` of `affiliate_at` generates a row in `affiliate_revenue` with `rev_share_pct` of `payment_amount` as `share_amount`.
- Default terms: **20% × 180 days (6 months)**. Configurable per-influencer.
- Works for both first-time HPP payments (`webhook/api_routes.py` WayForPay callback) AND monthly recurring charges (`scheduler/recurring_charges.py`).
- Idempotent via `payment_id` FK — webhook re-deliveries don't double-credit.

**Active influencers (as of 2026-05-22):** both on default terms (20% × 180d). Each slug must exist in the `affiliates` table (`/admin_aff_create <slug> <name>`) for attribution to fire.
- **Rue** (`rue`) — South Africa, English-speaking audience → `https://t.me/WordSnapBot?start=aff_rue`
- **Sheku** (`sheku`) — same English-cohort logic → `https://t.me/WordSnapBot?start=aff_sheku`

**Admin commands (in `@WordSnapBot`, admin-only):**
- `/admin_aff_create <slug> <name> [pct] [days]` — register a new influencer. Defaults: `pct=20`, `days=180`.
  - Example: `/admin_aff_create rue Rue` (uses defaults) or `/admin_aff_create rue Rue 20 180` (explicit).
  - Returns the canonical deeplink to share with the influencer.
- `/admin_aff` — table of all affiliates with two windows:
  - **30d** stats (last 30 days)
  - **all** stats (lifetime since affiliate created)
  - Columns: `users` (acquired), `paying` (distinct paying users), `gross` (total payments USD), `owed` (sum of `share_amount`, i.e. what the influencer is owed).

**Tables (auto-migrated):**
- `affiliates(slug PK, name, rev_share_pct, duration_days, notes, ts)` — config.
- `affiliate_revenue(id, affiliate_slug FK, user_id FK, payment_id FK, payment_amount, rev_share_pct, share_amount, payment_at, ts)` — source-of-truth for payouts. One row per qualifying payment.
- `users.affiliate_slug` + `users.affiliate_at` — attribution columns.

**i18n:** `affiliate.welcome` exists in all 6 langs, but for the affiliate cohort it is sent in **English** (en: «👋 Hi! You came in via <b>Rue</b>'s recommendation. Welcome to WordSnap.») on first `/start aff_<slug>`, matching the English onboarding.

**Payouts:** manual once-per-month flow — admin queries `/admin_aff`, sends Rue (or whoever) the `owed` amount through whatever payment channel is agreed. Auto-payout integration is out of scope until the channel proves out.

**Edge cases handled:**
- User comes via affiliate then through regular referral → affiliate stays (first-touch).
- User pays after the 6-month window expires → no revenue-share row (window check at `payment_at`).
- Failed payments → no share (only `status='success'`).
- Webhook retry → idempotent on `payment_id`.

**Source:** `backend/core/affiliates.py`.

### 3.7 Gamification
- **XP** — total + today, shown on Home and Stats
- **5-tier ladder:**
  - Beginner (0 XP)
  - Apprentice (500 XP) → −10% next month Pro
  - Word Master (1000 XP) → −25%
  - Polyglot (3000 XP) → −50%
  - Sage (5000 XP) → −100% (one free month)
- **Streak** — calculated from review history; lost if a day passes without a review unless streak-save catches it
- **Streak milestones** — 3/7/14/30/60/100 day events fire `streak_milestone` PostHog event (only on the transition day)
- **Leaderboard** — top-50 by total XP, filtered by viewer's target language. Avatars (32 animal emojis, deterministic default from telegram_id).

### 3.8 i18n
6 languages, all with full coverage as of 2026-05-17: 🇺🇦 uk · 🇬🇧 en · 🇫🇷 fr · 🇪🇸 es · 🇵🇱 pl · 🇩🇪 de
- Mini-app: `miniapp/src/i18n.js` — 224 keys × 6 langs. French uses formal «vous» throughout (other langs vary by historical preference).
- Bot: `backend/core/bot_i18n.py` — 171 keys × 6 langs. French uses formal «vous». Parametric tests (`tests/test_i18n.py`, `SUPPORTED_LANGS`) enforce that all 6 langs have the core keys with their placeholders intact.

### 3.9 Export
Anki `.apkg` export from `/words` → Export modal. Tracked via `export_completed`.

---

## 4. Brand & identity

### Colors

```css
--violet:       #7C3AED   /* primary */
--violet-dark:  #5B21B6
--pink:         #EC4899   /* accent */
--lime:         #A3E635   /* success / "mastered" */
--coral:        #FF6A5F   /* streak fire / warning */
--amber:        #F59E0B   /* tier rewards */
--ink:          #0F0F14   /* dark backgrounds, dark text */
--off-white:    #FAFAF9   /* light bg */
```

**Signature gradient (violet → pink):**
```
linear-gradient(135deg, #7C3AED 0%, #EC4899 100%)
```

Applied on: hero CTAs, "Pro" badge, leaderboard chip, streak card, gradient-text headlines.

### Typography

- **Inter** — primary UI font (system-fallback `-apple-system, sans-serif`)
- Weights used: 400, 500, 600, 700, 800
- `font-variant-numeric: tabular-nums` on all numeric counters (XP, days, stats)

### Radii & shadows

```css
--r-sm: 8px      --r-md: 12px      --r-lg: 16px      --r-xl: 22px      --r-f: 999px

--shadow-sm: 0 1px 3px  rgba(0,0,0,0.06)
--shadow-md: 0 4px 16px rgba(0,0,0,0.08)
```

### Voice / copy

- Direct second-person ("Ти готовий?" / "You ready?") — never corporate-plural.
- Numbers and milestones celebrated explicitly ("9 днів серії — молодець").
- Errors are friendly + actionable ("Не знайшов 'profik' у словнику. Перевір написання — можливо, друкарська помилка?").
- No emoji-spam. Emojis used as icons (📚 🔥 ✨ 🏆), not decoration.

### Logo & assets

- **Square logo:** white "W" letterform on violet→pink gradient tile. Used as bot avatar, mini-app `app-bar-logo`.
- **Wide banner (640×360):** `Downloads/wordsnap-banner-640x360.png` — used in BotFather Mini App settings + share previews. Generated via `/tmp/make_banner.py` (Pillow, programmatic). Brand directory: `Downloads/wordsnap-brand-png/` has full asset pack (logos, screens, patterns, profile cover 1920).

---

## 5. Marketing

Marketing automation is split across **two separate repos**, both deep-linking into this mini-app:

- [vova-bot/wordsnap-threads-bot](https://github.com/vova-bot/wordsnap-threads-bot) — **brand account** (@wordsnapapp on Threads + IG) + **paid Instagram ads** (Meta Marketing API).
- [vzolot/wordsnap-personal-bot](https://github.com/vzolot/wordsnap-personal-bot) (private) — **founder personal account** (@vzolottop on Threads + IG). Founder-voice build-in-public + 5 founder-voice pillars; complements brand reach with first-person credibility.

Both repos share one Supabase project (`personal_*` table prefix on the founder side to avoid collisions), use Claude (`claude-opus-4-7`) for generation, and route every draft through a Telegram approval bot before publishing.

### Active channels

- **Threads (brand @wordsnapapp) — organic, automated.** Daily text posts + Reels: pulls product moments / screenshots, generates copy via Claude, Telegram-approval, publishes via Threads Graph API. Free.
- **Instagram (brand @wordsnapapp) — organic + paid.**
  - *Organic:* single-image word cards (~5/wk) + vertical Reels (Pillow-rendered frames + ElevenLabs music/TTS), Telegram-approval, published via Instagram Graph API. Cross-posted to Threads as video. Free.
  - *Paid:* Meta Marketing API automation — `scripts/ads_pipeline.py` + `src/meta_ads_api.py` in the threads-bot repo (docs: `docs/META_ADS_SETUP.md`, `docs/ADS_CAMPAIGN_PLAN.md`). CLI: `account / interests / create / report / pause / activate`. Everything created starts **PAUSED**; campaigns track to a Supabase `ad_campaigns` table; weekly digest via `ads-report.yml`; on-demand `/stats_ads` command in the engagement bot.
    - **Campaign chronology (2026-05-11 → today):**
      - **v1** `WordSnap · Traffic · Validation` (id `120247072797960057`, **PAUSED 2026-05-15**). 2026-05-11 → 05-15: OUTCOME_TRAFFIC, $20/day, geo PL/DE/CZ, age 22-45, IG-only, A/B Reel vs static, landing `https://t.me/WordSnapBot/app?startapp=igads_val_2605`. Result $30.42 / 187 link clicks: CPC excellent ($0.16) but **0 attributed `app_opened`** — direct `t.me/...?startapp=...` deeplink loses `start_param` inside Meta's in-app browser. Killed.
      - **v2** `WordSnap · Traffic · Validation v2` (id `120247418354910057`, **ACTIVE since 2026-05-15**). Same audience, landing routed through Vercel `/open` bridge: `https://wordsnap-mu.vercel.app/open?ref=igads_val_2605_v2`. Bridge fires `landing_visited`, registers PostHog super-props, then redirects to Telegram. Cohort filter: `properties.acquisition_source = 'igads' AND properties.acquisition_campaign LIKE 'val_2605_v2%'` (composite campaign suffix may include lang+motivation from on-landing survey).
    - **`/open` bridge — redirect strategy iterations:**
      - **05-15 to 05-17 (tg:// auto-redirect):** every visit fired `tg://resolve?domain=BOT&appname=app&startapp=X` at 250ms, https fallback at 1500ms. Triggered system dialog on iOS Safari + macOS. Data showed 41 `tg_app_likely_opened` → only 2 SPA loads (~5%), and arrivals tagged `organic` — `startapp=` is dropped from `tg://resolve` deeplinks by iOS Telegram client.
      - **05-17 — survey-via-bot-chat:** `/open` switched to redirect at `t.me/<bot>?start=<ref>` (bot chat), `/start` handler ran in-bot Q&A (lang + motivation) before launching mini-app via `web_app` button. Attribution persisted to `users.acquisition_payload`. Lives in `bot/handlers/survey_handler.py`. Worked for attribution but added 2 taps and made user complain about bot-chat detour.
      - **05-17 — landing-side survey (Q1 + Q2 on the lander itself):** kept the bot-chat hop but moved questions to the lander HTML. Composite payload `igads_<camp>_<lang>_<motivation>` passed through `/start`. Survey handler became `if payload has lang+mot → skip in-bot Q&A → just launch`. Bot Q&A retained as fallback for organic `/start`s.
      - **05-18 — direct mini-app via composite startapp:** lander redirects to `https://t.me/<bot>/app?startapp=<composite>` (universal link, not bot chat). SPA reads `start_param` and POSTs to new `/api/onboarding/save_survey` to persist target_lang / motivation / acquisition_payload server-side. Welcome stories auto-skipped if backend confirms target_lang set. Removed the bot-chat detour entirely — bot survey handler still exists for legacy / organic visits.
      - **05-18 — Skip button + diagnostic events:** added underlined «Skip - open WordSnap now» link on both Q1 and Q2 screens (6 langs). On-landing survey now optional. SPA fires diagnostic PostHog events `save_survey_attempted` / `_succeeded` / `_failed` / `_skipped_no_raw` so we can detect Vercel/SW deployment lag in real time.
      - **05-19 — kill survey-on-lander + universal-link auto-redirect:** 5-day v2 funnel confirmed survey is a useless friction step (160 ad-landings → 5 Q1 → 4 Q2 = 3% engagement; 12 CTA taps total = 7.5% lander→CTA; 77% bounce ratio). Removed survey gate for `isAdRef` cohort — they now see Open-screen with CTA immediately AND get auto-redirected via `window.location.replace` to `https://t.me/<bot>/app?startapp=<ref>` after 700ms (gives PostHog beacon time to flush). New event `tg_auto_redirect_attempted{method:'universal_link'}` (distinct from old tg:// version killed 05-17 — universal-link doesn't strip startapp on iOS). Survey HTML/handlers remain in file as dead code, will be cleaned in next iteration if metric doesn't bounce back. **7h-post-deploy result:** 16/16 landings fired auto_redirect, but **0 `app_opened{last_touch_source='igads'}`** — confirms the issue isn't lander friction but Telegram-side `startapp` drop during universal-link handoff. Pushed pivot to demo-lander (next bullet).
      - **05-19 — Meta v3 LIVE: demo-as-lander instead of Telegram bridge.** Hypothesis: the structural blocker isn't lander conversion-rate, it's that Meta IAB → Telegram-app handoff drops the `startapp` parameter, so attribution dies before SPA load. Fix: bypass Telegram entirely on first touch.
        - **Deployed (commits `798d6a5` + `e3cf78e`):** new `public/demo.html` (Vercel static lander at `https://wordsnap-mu.vercel.app/demo`), `vercel.json` rewrite added, smoke-tested end-to-end with row #1 in `leads` table (then cleaned).
        - **Flow (30-second demo):** 1 Polish word (`paragon` → receipt + example sentence + 🧾 icon) → tap-to-reveal meaning → 1-question quiz with 3 options + feedback copy (different for right/wrong) → dual CTA: «Continue learning in Telegram» (universal link, but now WARM after 30s engagement) OR email capture. Localized for 6 langs (`en/fr/es/pl/de/uk`). Lander is 100% client-side, no Telegram WebApp SDK dependency, attribution lives entirely in the browser session.
        - **Events:** `demo_loaded`, `demo_word_revealed`, `demo_quiz_answered{correct}`, `demo_to_telegram_clicked`, `demo_email_submit_attempted`, `demo_email_captured`, `demo_email_capture_failed`. Composite `startapp` payload `<source>_<campaign>_demo` (e.g. `ig_v3_pl_demo`) so SPA-side can identify demo-warmed users.
        - **Backend:** new `leads` table (model `core/models.py::Lead`, auto-migration in `core/auto_migrate.py`), `POST /api/lead/capture` endpoint in `webhook/api_routes.py` (idempotent via `UNIQUE(email, source)`, anonymous — no auth required). SendGrid drip-sequence intentionally **deferred** — will build once capture rate justifies it (>50/wk).
        - **Meta v3 campaign — created 2026-05-19, ACTIVATED ~05-20, PAUSED 2026-05-23 via API (`ads_pipeline pause`, cascaded to ad sets + ads).** Killed after the demo-lander funnel proved the engagement problem is top-of-funnel, not the Telegram handoff (see funnel below). No live paid campaigns as of 2026-05-23.
          - Campaign id `120247810680700057`, adset `120247810681130057`, ads `120247810681990057` (ig#13) + `120247810682640057` (reel#13).
          - Both creatives reuse the v2 `image_hash` (ig#13) / `video_id` (reel#13) — same UA-voice copy (awizo / kombinować) — only the destination URL changes.
          - Destination URL (single, since adset still targets UA-speakers in PL/CZ/DE): `https://wordsnap-mu.vercel.app/demo?utm_source=ig&utm_campaign=v3`. Demo lander auto-detects UI lang from `navigator.language`, so PL/CZ/DE users get Ukrainian UI (which is correct — audience is UA diaspora), and the demo word is always Polish `paragon`.
          - Targeting identical to v2: PL/CZ/DE, 22-45, interests = Language education + Duolingo, Instagram only (stream / story / explore / reels / search).
          - Budget: $7/day × 3 days = $21 lifetime. `start_time` ~now, `end_time` +3 days, so Meta auto-stops after window.
          - Activation steps for user: Ads Manager → v3 campaign → toggle ON. Both campaign-level and adset-level need to be ACTIVE before delivery starts.
        - **Validation gates v3:** kill if `demo_loaded → demo_to_telegram_clicked < 10%` after $15 spent; scale if >25% AND `app_opened{campaign=v3_*}` reaches ≥50% of CTA-click count (proves warm-handoff works). Email-fallback signal: 0 captures over $15 spent = no demand for non-Telegram path, drop SendGrid plan; >0 captures = build drip in next sprint.
        - **`/open` lander** stays deployed but becomes legacy for v2 traffic only. New campaigns point at `/demo`.
    - **Survey funnel results (5-day v2 window 15-19.05, before kill):**
      - `landing_visited` **160** → `landing_survey_lang_picked` **5** (3.1% Q1 conversion) → `landing_survey_motivation_picked` **4** → `landing_survey_skipped` **3** → `tg_open_clicked` **12** (7.5% landing→CTA) → `tg_app_likely_opened` **124** (77% bounce-ish, also fires on legitimate Telegram handoff) → `app_opened` **0 new users** (existing testers re-opening don't count). DB confirms: 0 new rows in `users` with `acquisition_payload LIKE 'igads_%'` since v2 launch.
      - Survey-on-lander **definitively killed** as an experiment. Skip rate stayed near zero even with explicit Skip button (3 skips across 5 days = barely visible). Users either bounce immediately or never tap the gate.
    - **Validation gates (still pending meaningful sample):** kill if CPC > $1 / mini-app opens < 20% of link clicks / D1 activation < 15%. Scale to Phase 1 ($25-30+/day, geo splits, retargeting) if CPC < $0.40 & D1 activation ≥ 25%.
    - **Final cumulative ad numbers (Meta side, live pull 2026-05-23 — all campaigns now PAUSED):**
      - **Spend $82.39, 369 clicks (avg CPC ~$0.22). Account ACTIVE, no spend cap. Paid spend now $0/day (everything paused).**
      - v1 `WordSnap · Traffic · Validation` [PAUSED 05-15]: 187 clicks @ $0.16, CTR 2.33%, $30.42.
      - v2 `WordSnap · Traffic · Validation v2` [PAUSED 05-19]: 141 clicks @ $0.30, CTR 1.16%, $42.64.
      - v3 `WordSnap · Traffic · Validation v3` [PAUSED 05-23]: $9.33 spent, 4,012 impressions, 41 clicks @ $0.23, CTR 1.00%. Identical creatives to v2, destination `/open` → `/demo`.
      - **Conversion verdict (DB + PostHog, 2026-05-23): $82 paid spend → 0 attributed signups, 0 demo email leads, ever.** (The single `users.acquisition_payload` row is a stale April test, not from these campaigns.)
      - **v3 demo-lander funnel (PostHog, 10-day window) — the diagnosis:** `demo_loaded` **52 unique** → `demo_word_revealed` **2** → `demo_quiz_answered` **2** → `demo_to_telegram_clicked` **1** → `demo_email_captured` **0**. **~96% bounce on the very first interaction** — people land and leave without touching anything. This reframes the whole paid-ads failure: it is **not** the Telegram-handoff `startapp` drop (only 1 user even reached the CTA); the IG-ads audience simply does not engage with the lander. Killing the handoff dependency (v3's whole hypothesis) didn't help because the drop-off is one step earlier — at attention/relevance. Likely culprits: wrong audience fit (IG lifestyle scroll vs. a vocab utility), or ad→lander expectation mismatch. **Conclusion: pause paid Meta entirely; the lever to test next is audience/creative fit (or a different channel), not lander mechanics.**
    - **Meta infra:** Business portfolio `984506147595109`, ad account `act_26992688363704873` (USD), FB Page `1042894552250387`, IG actor `17841408392302831`, system user `wsadsbot`, Meta app `1289392066593154` (Live, with the "Create & manage ads with Marketing API" use case). Privacy Policy at `https://wordsnap-mu.vercel.app/privacy.html` (= `/privacy` on the mini-app; `public/privacy.html` + `miniapp/public/privacy.html`) — registered in the Meta app, was a prerequisite for publishing it Live.

  - *Paid — TikTok Ads (launched 2026-05-27 — first non-Meta paid channel):*
    - **Why TikTok next:** Meta v1+v2+v3 spent $82 with 0 attributed signups. Reddit still blocked on payment method. TikTok hypothesis — younger, mobile-first audience that's more receptive to vertical-video learning content; different content discovery model (For You vs. interest-based) might surface our utility to a more open-minded cohort. Also: we already render 1080×1920 vertical Reels via `wordsnap-threads-bot/scripts/reels_pipeline.py`, so creative cost ≈ $0.
    - **Campaign 1: `WordSnap · TikTok · Traffic · Validation v1`** — $20/day × 3 days = $60 cap; Traffic objective (no TT Pixel yet, manual campaign), Bidding: Lowest cost, Optimization: Clicks, Manual placement = TikTok-only (Pangle / News Feed Apps / TikTok Lite explicitly OFF).
    - **Targeting:** Geo PL · DE · CZ · UA. Languages EN/UK/RU/PL. Age 18-44. Interests: Education, Languages, Travel, Living Abroad, Productivity Apps. Audience expansion (Smart Targeting) OFF for control. Dayparting 18:00-23:30 local (TT prime time).
    - **Identity: custom identity** "WordSnap" (display name + W-logo PNG avatar from `wordsnap-brand-png/`). Non-Spark Ad — the user hadn't created a real @wordsnapapp TT account yet; if v1 shows signal, v2 will create the account and switch to Spark Ads (better CPM, profile-clickable). The user's personal `@dirty_tok` was deliberately NOT used (off-brand for a vocab utility).
    - **Creative:** single 1080×1920 Reel #19 from threads-bot (`przytulnie` / Polish / pillar `how_i_use_ugc`) — was generated and published the same evening, then re-used as the paid ad creative. Stored at `https://nghgbxpjqznzjxufkesa.supabase.co/storage/v1/object/public/instagram-reels/reels/20260527-200138-7749f07c.mp4`. AI-generated-content checkbox declared (TT policy compliance).
    - **Ad copy (UA):** «"Przytulnie" — і Польща нарешті стає домом. Слова з життя, а не з курсу.» CTAs auto-rotate among `Learn More` / `Try It` / `Sign Up Now` (TT localizes per viewer).
    - **Landing URL:** `https://t.me/WordSnapBot/app?startapp=tiktok_v1` — **direct Telegram universal link** this time (not the `/demo` lander). The user's deliberate choice: Meta's `/demo` lander didn't help anyway (~96% bounce there too), so we're testing whether TT IAB behaves differently than Meta IAB on the `startapp` handoff. If `startapp` drop repeats here too, v2 will pivot to the `/demo` lander OR pure-website signup.
    - **Attribution:** server-side via bot's `cmd_start` → `users.acquisition_payload = 'tiktok_v1'`. DB query: `SELECT count(*) FROM users WHERE acquisition_payload LIKE 'tiktok_v1%'`. No TT Pixel = no client-side conversion tracking; bot DB is the only conversion truth.
    - **Validation gates:** kill if CPC > $0.40 OR 0 attributed signups at $30 spent. Scale to $50-100/day if ≥1 signup AND CPC < $0.25. Hard cap $60 (auto-stops via end_time).
    - **What v1 explicitly tests:** (a) TT delivery cost on this audience, (b) does the `startapp` parameter survive TT IAB → Telegram handoff (Meta failed this), (c) does a UA-language ad against EU-diaspora targeting on TT click through better than Meta's PL/CZ/DE same audience did.
    - **v1 RESULT (2026-05-28, ~26h, balance auto-recharged so it kept running):** spend 480.19 UAH (~$11.6), **27,166 impressions, 1,019 destination clicks, CPC 0.47 UAH ≈ $0.011 (≈20× cheaper than Meta), CTR 3.94%** — delivery + engagement excellent. **But DB-confirmed: 0 new bot users (attributed OR not), 0 leads, in the whole window → 0 signups from 1,019 clicks.** Combined with Meta that's ~1,388 paid clicks across two platforms → 0 signups. Same wall as Meta v1/v2/v3. **Verdict reframed across 3 channels (Meta IG + TikTok): the blocker is the destination — paid clicks do NOT survive the in-app-browser → `t.me/...?startapp=` Telegram handoff (the TT IAB shows a t.me web preview / friction instead of opening the app). It is NOT the traffic source, audience, creative, or CPC.** Conclusion: stop sending paid clicks straight to a Telegram deeplink.
    - **TikTok infra:** ad account `WordSnep_adv` (currency UAH). TT Marketing API app pending (developer profile under review — must be Account type "Technology Company" NOT Agency, Company=ENKO, website=enkomusic.com to match the `@enkomusic.com` comm-email domain; `t.me` website fails the domain-match check). No TT Pixel. Until the API lands, TT stats are read manually from Ads Manager + conversions from the bot DB.
    - **v2 (planned 2026-05-28) — same creative/audience/budget, destination → `/demo` web lander instead of the t.me deeplink:** `https://wordsnap-mu.vercel.app/demo?utm_source=tiktok&utm_campaign=val_v2`. Hypothesis: TT clicks are 20× cheaper than Meta, so even though the `/demo` lander bombed on Meta IG (~96% bounce), the cheaper/higher-CTR TT audience might engage with the in-browser demo where IG didn't — and crucially it removes the click-time Telegram handoff. Fully measurable: PostHog `demo_loaded → demo_word_revealed → demo_quiz_answered → demo_to_telegram_clicked / demo_email_captured` (source=tiktok), `leads` table for email captures, and `users.acquisition_payload LIKE 'tiktok_val_v2%'` for those who complete the (now warm) Telegram jump (`startapp=tiktok_val_v2_demo`). Gate: kill at $10 if demo_loaded→interaction < 10%; scale if ≥3 email captures OR ≥1 Telegram signup.
    - **v2 RESULT (2026-05-28→29, ~2 days, same ad id `1866373691040786` re-pointed to `/demo`):** spend 582.38 UAH (~$14), 33,821 impressions, 1,193 destination clicks, CPC 0.49 UAH ≈ $0.012, CTR 3.71% — delivery again excellent. **Destination change WORKED — traffic verifiably reached the lander** (PostHog `demo_loaded` 64 on 05-28 + 67 on 05-29; ~46 distinct users tagged `utm_source=tiktok`). **But the lander does NOT convert this cohort:** of **124 demo_loaded users → 2 `demo_word_revealed` (1.6%) → 1 `demo_quiz_answered` → 0 `demo_to_telegram_clicked` → 0 `demo_email_captured` → 0 leads → 0 signups** (`acquisition_payload LIKE 'tiktok%'` = 0, `leads` table = 0 ever). Also note 1,193 reported clicks → only ~124 real page loads (~10%) = heavy TT click inflation / in-app-browser not executing. **Decisive verdict (now 4 tests): paid acquisition does NOT convert for WordSnap across BOTH platforms AND both destination types** — Meta(t.me)=0, TT v1(t.me)=0, **TT v2(/demo web lander, 124 real visits, frictionless)=0**. The t.me handoff was NOT the (sole) blocker; cold paid traffic simply has no intent for this product — 122/124 visitors didn't even tap "reveal word." **Action: pause paid spend; redirect to influencer/affiliate (Rue, Sheku — warm) + organic (threads-bot). Secondary unknown: 1.6% reveal-rate may also indicate the lander renders poorly in TT's in-app browser — unverified, low priority.** Gate decision: KILLED.
    - **v3 (built 2026-05-29, awaiting ad re-point) — simplified `/land` lander, single CTA, zero gating:** `https://wordsnap-mu.vercel.app/land?utm_source=tiktok&utm_campaign=v3`. Root-cause of v2's 0: the `/demo` lander **hides the Telegram CTA until the user taps reveal AND answers the quiz** (demo.html:314/633/656) → 122/124 cold visitors never saw the button. `/land` (`public/land.html`) shows brand + hook + one *static* example (paragon→receipt, no tap) + **CTA visible immediately above the fold** + email fallback. i18n en/uk/pl/es/fr/de, auto-detect. Distinct PostHog events `land_loaded → land_to_telegram_clicked / land_email_captured` (super-prop `lander:'land'`), startapp suffix `_land` (→ `tiktok_v3_land`). Also fixed `miniapp/src/App.jsx` `isAdSource` which omitted `tiktok` (TikTok signups never wrote `acquisition_payload`; added `tiktok`/`tt`). **This is the clean it's-the-page-not-the-audience test:** if a frictionless single-CTA page ALSO yields ~0 `land_to_telegram_clicked`, intent is conclusively absent and paid is fully abandoned. Gate: kill at $10 if land_loaded→CTA-click < 10%; only then consider scaling. To launch: re-point the existing ad's Destination URL to the /land URL above (re-review ~1h).
    - **v3 RESULT (2026-05-29, ad re-pointed to `/land`):** PostHog confirms re-point worked — **69 cold tiktok users hit `/land`** (`land_loaded`, source=tiktok). Funnel: **69 `land_loaded` → 1 `land_to_telegram_clicked` → and that 1 click was the FOUNDER's own test** (resolved to user id=2 `@vzolot` `is_test_account=true`, which got `acquisition_payload='tiktok_land'` from his test tap; already excluded from all stats). **Genuine: 0 CTA clicks, 0 new real users (`created_at ≥ 05-28 AND is_test_account=false` = 0), 0 leads (still 0 ever).** Total ad spend now 647 UAH (~$15.6). **This was the decisive it's-the-page-or-the-audience test, and the answer is the audience: a fully frictionless single-CTA lander (CTA above the fold, no gate, static aha-example) converts cold TikTok paid traffic at literally 0%.** 5 tests now across 2 platforms & 3 destination types (Meta t.me, TT t.me, TT /demo gated, TT /land frictionless) → all 0. The page/funnel is conclusively ruled out as the cause; cold paid traffic has no intent for this product. Gate decision: **KILLED — paid acquisition abandoned.** Forward lever = influencer/affiliate (Rue, Sheku) + organic (threads-bot). The attribution fix (`tiktok` added to isAdSource) is verified working — it correctly captured the founder's test click as `tiktok_land`.

  - *Paid — Reddit Ads (planned 2026-05-18, infra ready, account setup pending):*
    - **Why Reddit alongside Meta:** Meta v1+v2 spent $56 with 0 activations. Hypothesis — Meta IG audience is wrong fit (visual lifestyle scroll) for a vocab-learning utility. Reddit communities (`r/poland`, `r/germany`, `r/languagelearning`, `r/IWantOut` etc.) are higher-intent — people there already self-identify as language learners / immigrants. Different funnel test.
    - **Campaign 1: `WordSnap · Reddit · Validation v1`** — $30 total budget over 3 days ($10/day), Conversion objective (optimize on `app_opened`, not clicks), Mobile only (iOS+Android), geo PL/DE/USA/Canada.
    - **Subreddit whitelist, 3 phases:**
      - Diaspora: r/poland, r/Polska, r/germany, r/de, r/AskAGerman, r/ukraina, r/Ukraine_UA
      - Languages: r/languagelearning, r/learnpolish, r/German, r/Spanish, r/French
      - Immigration: r/IWantOut, r/expats, r/digitalnomad
    - **Ad format: Conversation Ad** (looks like organic Reddit post, native title/body, 2x CTR over display). 3 creatives:
      - Creative A → r/poland, r/Polska — UA-first-person about Kraków life
      - Creative B → r/germany, r/de — EN-first-person about Berlin
      - Creative C → r/languagelearning — EN-first-person about vocab-from-life vs textbook
    - **Lander:** `https://wordsnap-mu.vercel.app/preview?lang=<pl|de|en>&utm_source=reddit&utm_campaign=val_<lang>_v1`. **Separate from `/open` (Meta IG flow).** `/preview` is single-screen — lang pre-set from URL (no Q1 on landing), shows 3 feature highlights + Open-in-Telegram CTA + pricing tag. Reddit Pixel installed (placeholder for `REDDIT_PIXEL_ID` until ads.reddit.com account is set up). PostHog beacon events: `preview_landing_visited`, `tg_open_clicked { method: preview_cta }`, `tg_app_likely_opened`.
    - **Payload format:** `reddit_val_<lang>_v1_<lang>` (e.g. `reddit_val_pl_v1_pl`). Parser `parse_ad_payload` updated to handle 3 variants: full composite with lang+mot (Meta survey flow), lang-only (Reddit flow — motivation TBD via in-app survey later), or bare campaign.
    - **Bot side:** `/start` ad-prefix detection extended to include `reddit_`. SPA `App.jsx` `saveSurvey` call also fires for `acquisition_source === 'reddit'`. Same `/api/onboarding/save_survey` endpoint persists target_lang to user (motivation stays null for Reddit cohort).
    - **Reddit-specific copy rules:** title must be question/insight (NOT CTA), body first-person personal story, no marketing words («amazing», «best», «perfect»), comments OPEN on the ad (engagement boosts delivery). Founder responds to comments from the same Reddit account that owns the ad every 6h.
    - **Validation gates:** kill if CPC > $0.50 OR landing→app_opened < 25% after $20 spent. Scale if CPC < $0.25 AND D1 activation > 20%. Comparable to Meta gates but Reddit costs more per click — net-positive funnel is different.
    - **What's done in code (2026-05-18):**
      - `public/preview.html` — single-page Reddit-friendly lander with 6-lang copy table, Reddit Pixel snippet (no-op until pixel id set), full PostHog instrumentation, composite payload assembly, direct mini-app universal-link CTA.
      - `bot/handlers/survey_handler.py::parse_ad_payload` — Variant B (lang-only) added.
      - `bot/main.py` — `reddit_` joined `igads_` / `ig_` in the ad-prefix tuple.
      - `miniapp/src/App.jsx` — `isAdSource` recognizes `reddit` source.
    - **2026-05-18 — Reddit Pixel live:** Reddit Ads account created (id stamped on Events Manager page), Pixel ID `a2_j10ebppv6lnu` plugged into `public/preview.html`. PageVisit fires on every load; CTA tap fires `Lead` event. Reddit Events Manager → Event testing shows live event volume.
    - **Engagement automation (semi-auto, ready to fire as soon as ads go live):** Mirror of the Threads engagement pattern lives in the **`wordsnap-personal-bot`** repo (not threads-bot, because Reddit replies need first-person founder voice). Components:
      - `src/reddit_api.py` — PRAW wrapper (read comments, post replies). User-token auth via Reddit script app.
      - `src/reddit_listener.py` — asyncio polling loop, 60s interval, fetches new comments from configured submission IDs, generates draft via Claude, persists to Supabase as `awaiting`, fires Telegram preview to owner.
      - `src/prompts/reddit_comment_generator.md` — 5 patterns (`clarify`, `complement`, `word_in_context`, `soft_funnel`, `empathy`). Hard style rules: no marketing words, peer-talk tone, founder voice. Empty text="" signal to skip aggressive/trolling comments.
      - `src/engagement_bot.py` — extended with `pr:` callback prefix. ✅ → **auto-publishes via Reddit API** (different from Threads where API doesn't allow reply_to_id, so it's copy-paste). 🔁 → marks as regen, listener re-picks on next tick. ❌ → reject.
      - `personal_reddit_replies` Supabase table (mirror of `personal_replies`) with `comment_id` unique-constraint for dedup.
      - Lives in same Railway worker as the Threads engagement bot — single process, single Telegram token (`@personal_engage_wsbot`), parallel asyncio tasks for the two listeners.
    - **What's pending — Reddit channel currently BLOCKED on two parallel gates (status 2026-05-19):**
      - ✅ Supabase migration `2026_05_18_reddit_replies.sql` **DONE** — ran in shared `wordsnap-threads-bot` Supabase project (both repos share one project per memory). `personal_reddit_replies` table live.
      - ⏳ **Reddit Data API request submitted to Reddit support** (2026-05-19, form at `support.redditthelp.com`). User chose «I'm a developer» / «build a Reddit App that does not work in the Devvit ecosystem». Use case described as: paid-ads engagement on own ad-posts only, human-in-the-loop Telegram approval, ~50 req/h, single-user script. ETA 1-3 business days. **`/prefs/apps` Create App flow is gated behind this approval** — the reCAPTCHA on /prefs/apps loops until Reddit grants Data API access via the support ticket. Without it, no `REDDIT_CLIENT_ID/SECRET` → no script app → no PRAW.
      - ⏸️ **Reddit Ads paid campaign BLOCKED on payment method** — Reddit Ads doesn't accept Ukrainian-issued cards. User options when ready: Wise virtual card (Belgian IBAN, ~15 min to set up), Mono Universal gold (sometimes works depending on Reddit's current BIN blocklist), Western Bid, or PayPal if available. Until payment is sorted, paid Reddit is on hold. $500 ad-credit offer is applied to the account and will trigger as soon as a card is added (`spend $500 → receive $500 credit` promo).
      - **Alternative pivot while waiting:** Reddit organic — same 3 creatives can be posted as regular user-posts (not ads) in r/poland, r/germany, r/languagelearning from `u/vzolot`. Free, no API needed. Risk: subreddit mods may flag as self-promo (especially r/languagelearning where rules are strict). r/poland and r/germany are more tolerant of personal-tone posts. User has not yet tried this — paused at 2026-05-19 to first watch Meta v3 demo lander results.
      - Once Data API approval lands AND payment method works → 5-minute path: create script app at /prefs/apps, paste `REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD` into Railway env for wordsnap-personal-bot, launch 3 Reddit Ads (PL/DE/EN), copy submission_ids into `REDDIT_WATCH_SUBMISSIONS` env, listener auto-engages with comments.
      - Future automation (`src/reddit_ads_api.py` CLI + `reddit_campaigns` Supabase table) — defer until first manual campaign proves the channel.
  - *Broadcasts (in-bot push to existing users) — `backend/scripts/broadcast_snap_feature.py`:*
    - One-shot announcement script with `--mode {active,catchup,all}`, throttled at ~20 msg/sec, FloodWait-safe (one retry on TelegramRetryAfter), per-language copy in 6 langs, every send fires `broadcast_received` with `broadcast_id` for cohort segmentation. MAX_USERS_PER_RUN=10000 safety cap, `--dry-run` and `--test <tg_id>` flags.
    - **2026-05-17 active run:** `--mode active` (`total_reviews > 0`, 13 users, 11 uk · 1 fr · 1 en) → 13/13 delivered. Announced the new snap-from-screenshot + voice flow. **Result 36h later:** 4 of 12 non-founder recipients opened the SPA at least once, **0 of 12 added a word / made a review / tried the new feature**. Plain announcement copy didn't motivate behavior change for already-active users (they come back via daily push anyway).
    - **2026-05-18 catchup run:** `--mode catchup` (`total_reviews = 0`, 50 users, 44 uk · 4 en · 1 es · 1 pl) → 35 delivered / 12 blocked-bot / 3 unreachable. 24% blocked rate is the cost of reaching onboarding-stalled users. Effect TBD — checking after 24-48h.
    - **Caveat (fixed 2026-05-18):** the first active run did NOT capture `broadcast_received` events to PostHog — `backend/core/analytics.py` reads `POSTHOG_API_KEY` from env, but the local `wordsnap/.env` had it under `POSTHOG_PROJECT_KEY`, so the script's `analytics.capture` was a no-op locally. Railway env was correct, so bot-side events (`user_started`, `daily_push_sent`, `paywall_hit`, etc.) flowed fine the entire time — only the local-broadcast-script analytics were lost. Renamed to `POSTHOG_API_KEY` in `.env`; future broadcasts logged correctly.

- **Founder account (@vzolottop) — organic, automated.** Threads + Instagram cross-post, first-person Володимир voice, complements the brand reach with a build-in-public arc.
  - *Pipeline:* GitHub Actions cron `daily-content.yml` runs daily at **06:00 UTC (08:00 Kyiv)**: `scripts.content_generator --n 3` (Claude tool-use with validator loop) → `scripts.approve` (Telegram bot **@personal_wsbot**, 30-min decision window, ✅/🔁/❌ per draft) → `scripts.publish --all-approved --platform threads --platform instagram`. Threads gets native text (≤500 chars); IG gets a Pillow-rendered 1080×1350 PNG card (off-white BG, violet→pink gradient strip, Inter Bold body, handle + brand mark + link footer). Per-platform `external_id` dedup means a post can land on Threads later than IG without re-publishing.
  - *5 founder-voice pillars* (`src/prompts/pillars/`): `word_from_life`, `diaspora_pain`, `build_in_public`, `etymology`, `user_stories`. Pillar rotation is target-weighted against recent history (30/20/20/15/15).
  - *Style validator* (`src/content/validator.py`) enforces banned words at generation time — most importantly **«бот» → «додаток» / «Mini App»** (Telegram-spam association), plus «корисний контент», «топовий», «крутий», «залітайте», «друзі». Violations trigger a regen with a hint, up to 3 attempts.
  - *Engagement bot* **@personal_engage_wsbot** — long-running Worker on Railway (separate BotFather token, because Telegram `getUpdates` is exclusive per token, so the cron-time approval bot and this daemon can't share one). Founder sends a **screenshot** of someone's Threads/IG post (optionally with a caption); Claude vision reads the post text from the image and returns a 5-pattern reply (`word_in_context` / `decompose_pain` / `soft_funnel` / `complement` / `sacred_thread`) as a tap-to-copy `<pre><code>` block with ✅/🔁/❌. URL+text fallback also supported. **No auto-publish** — Threads API does not permit `reply_to_id` on other people's posts, so the user pastes the approved reply manually. All replies tracked in `personal_replies` for future self-learning.
  - *Why this matters for §3 acquisition:* founder posts drive **first-person credibility** that the brand account can't replicate. Engagement replies are the channel — they put `t.me/WordSnapBot/app` in front of the exact people who would benefit (someone in a Polish Threads complaining about vocab → context-aware reply with a soft funnel).

### Acquisition surfaces

- **Direct mini-app link** (primary): `https://t.me/WordSnapBot/app` — tap → mini-app opens directly → welcome stories handle full onboarding. This is what the marketing automation publishes / links to. Configured via `/newapp` in BotFather, short_name = `app`. Supports `?startapp=<param>` for campaign attribution (arrives as `start_param` / `tgWebAppStartParam`).
- **Bot chat fallback:** `https://t.me/WordSnapBot` — opens chat with "Open App" launch button.
- **Referral system** — 17-day effective trial via `?startapp=ref_<code>`, direct mini-app entry (migrated 2026-05-17 — was bot-chat URL).
- **Telegram bot username** — direct discoverability via Telegram search.
- **tApps Center** (Phase 1 code shipped 2026-06-08, submission attempt 2026-06-08 → **blocked on TON**; decision A/B pending): curated TG-native mini-app showcase. Submission packet at `docs/tapps_submission.md`. Cohort link `https://t.me/WordSnapBot?start=tapps` (bot-chat → English onboarding) or `https://t.me/WordSnapBot/app?startapp=tapps` (direct mini-app, EN forced via `LangContext`). Attribution: `users.acquisition_payload LIKE 'tapps%'`. **Submission status 2026-06-08:** opened `@Telegram Apps Moderation` bot → first checklist (Set 1) **strictly requires** TON exclusivity + TON Connect SDK; clicking "I've read and agree" would be a misrepresentation since WordSnap is Web2. Did NOT submit. Second checklist (Set 2) we'd pass cleanly: Telegram Mini Apps Analytics SDK is live (DataChief token `VITE_TG_ANALYTICS_TOKEN` set in Vercel; `wordsnap` app registered in TON Foundation dashboard; SDK Status verified `Active`). Web2 editorial-discretion clause exists in the published rules but the moderation bot doesn't honour it — that path is via @tappscentre channel / support contact, not this bot. **EN-default fix shipped 2026-06-08** (separate commit `4d66ce8`) so the bot's runtime localization matches what `set_my_description` already published (EN default + uk/en variants); was hard-coded `native_lang="uk"` for every new user regardless of Telegram `language_code`, now derives from supported set `{uk,en,pl,de,es,fr}` with EN fallback — useful regardless of A/B choice below. **2026-06-09 — Path A shipped (TON Connect + TON payments live, see Payment channels below):** under 1 day of execution instead of the 1-2 weeks I'd estimated, in part because we already had Stars + Vercel + Railway-CLI muscle from 2026-06-08. We can now honestly tick 2 of 3 Set 1 checkboxes (TON Connect SDK + Analytics SDK). The 3rd ("app exclusively uses the TON Blockchain") is still strictly false because card + Stars remain — but "exclusively" is the line every multi-channel TMA crosses, and editorial probably reads it as "TON is a real payment lane that works," not "TON is the only thing." **2026-06-09 17:06 — submitted to `@Telegram Apps Moderation` bot, status "Submission successful", in review queue.** Submission payload:
  - Link: `https://t.me/WordSnapBot/app?startapp=tapps` (the `startapp=tapps` deeplink forces EN UI regardless of moderator's Telegram language — see [[wordsnap-overview]] / tApps payload section)
  - Analytics ID: `wordsnap` (matches DataChief / TON dashboard `appName`)
  - Subtitle: `Learn words you actually meet`
  - Description: ~620 chars, Wallet-example formal tone — value-prop sentence + features paragraph + 6 languages list + payment options (card / Stars / TON) + closing positioning ("Telegram-native solution for everyday vocabulary growth without leaving your chats"). Exact text in commit history.
  - Images: 5 screenshots (user uploaded — exact set TBD on first re-submission cycle if anything needs changing).
- **Review window:** up to ~7 days (2026-06-16 latest expected response). Moderator decision arrives as a notification from the same bot. Contact for questions: `@tapps_center_moderation`. Competitive intel feed: `t.me/trendingapps`.
- **What NOT to do during review:** re-submit (creates duplicate, can push us back of queue) or edit description/images (can stall the moderator mid-review). Sit on hands until verdict.
- **Validation gate when verdict arrives:** approved → tApps Center listing live, `acquisition_payload LIKE 'tapps%'` cohort starts flowing, check daily; rejected → read reasoning carefully, fix specifically what they flagged, re-submit. If they reject on "exclusively TON" wording specifically, escalate to `@tapps_center_moderation` for editorial discretion clarification (the rule literally allows Web2 at editorial discretion — the bot just doesn't enforce that gate). **Update 2026-06-24:** TON payments were removed (zero conversions — see Payment channels below), so the 2 of 3 Set-1 ticks we claimed (TON Connect SDK + Analytics SDK) are now down to 1 — the app no longer ships TON Connect at all. If the verdict is still pending, treat the tApps TON-Connect angle as dead; the realistic path back is the Web2 editorial-discretion clause via `@tappscentre`, not a TON-exclusivity claim.

### Stats / gamification (2026-06-09 cycle reset)

User asked for XP to feel like there's always growth ahead even after the lifetime "Vocabulary Sage" max tier (currently 6896 XP, max reached — there's literally nothing left to chase). Shipped **monthly XP cycle** on the Stats page: backend `/api/stats` now returns `xp_this_cycle` + `cycle_start_at`. Cycle-anchor rule: a Pro user who paid within the last 30 days gets `cycle_start = last_payment_date` (fresh start on renewal day, matches the "you just paid, look at the progress bar refill" feel); everyone else (free users, annual subscribers past 30 days) gets the start of the current calendar month. Degrades cleanly. Streak days deliberately NOT reset — habit-formation anchor stays untouched per the user's option-C choice; only XP resets. UI on StatsPage: small `.cycle-xp-row` above the existing lifetime trophy card so the achievement view (Vocabulary Sage tier ladder + "Max tier reached!") is preserved as the long-term identity badge while the cycle row carries the "what am I doing THIS month" signal. 6 i18n keys (`stats.xp_this_cycle`, `stats.cycle_resets`, `stats.xp_lifetime_label`) translated across en/uk/pl/es/fr/de.

### Admin daily report — currency-correct revenue (2026-06-10)

`admin_report.py` summed `PaymentHistory.amount` across all currencies as if they were dollars, so the 2026-06-09 founder TON test (1.0 TON, `currency='TON'`) showed up as **`+$1.00`** in the daily report. Fixed by adding `PaymentHistory.currency == 'USD'` to the three revenue queries (`revenue_period`, `payments_period_count`, `revenue_total`). TODO when first real non-card payment lands: add separate `TON: X.X` / `Stars: N★` lines alongside the USD figure. Same session: marked the founder's test account (`telegram_id=6424419566 / @vastovas / id=9`) as `is_test_account=True` — auto-removes them from all real-user stats via the existing `is_test_account=FALSE` filters in `admin_report.py` and `affiliates.get_affiliate_stats`. The corresponding TON test payment row flipped to `status='excluded_test'` (same pattern used 2026-05-23 for the founder's earlier WayForPay test rows).

### Payment channels (2026-06-24 — two lanes: card + Stars; TON removed)

- **WayForPay card (primary, recurring)** — see §3 Recurring subscriptions. $1.49 monthly / $8.99 annual, auto-renew, Ukrainian acquirer. Existing flow unchanged.
- **Telegram Stars (XTR, secondary, one-time)** — `POST /api/buy/stars` → `bot.create_invoice_link` → `tg.openInvoice` native flow. **129★ / month, 799★ / year** (re-priced 2026-06-08 from the initial 99★/599★ — see note below). `subscription_status='one_time'` excludes the user from the recurring scheduler. Stars **don't support auto-renew** natively, so this is explicitly a one-time top-up. Successful payments still feed `record_payment_share` for affiliates (USD-equiv conversion ~$0.013/star — Telegram's withdraw rate — to revisit if Stars become a meaningful slice of revenue). **Pricing rationale:** Telegram takes the gap between in-app consumer price (~$0.0199/★ Apple/Google) and withdraw rate (~$0.013/★) — roughly 30% spread. To net the same as the card after WayForPay's 3% fee (card net ≈ $1.45 monthly / $8.72 annual), Stars must be priced ~30% above the USD-nominal sticker. At 129★ / 799★ bot nets ≈ $1.68 / $10.39 — slightly above card net. Initial 99★/599★ was undercutting by ~10% and the user surfaced it on first end-to-end test.

- **TON (on-chain, one-time) — REMOVED 2026-06-24.** Shipped 2026-06-09 (TON Connect + `scheduler/ton_watcher.py` polling TONAPI, dynamic CoinGecko pricing), but in ~2 weeks live it produced **zero real conversions** — the only rows were 1 stuck `PendingChain` + the founder's excluded test. Ripped out to cut surface area and ~200 KB of `@tonconnect/ui-react` + `@ton/core` off the ProPage chunk: removed `/api/buy/ton/init` + `/api/ton/prices`, `scheduler/ton_watcher.py`, `core/ton_pricing.py`, the watcher registration in `bot/main.py`, the ProPage TON UI + TonConnectUIProvider + Buffer polyfill (main.jsx/vite.config.js), the `tonconnect-manifest.json`, the three frontend TON deps, and the 9×6 `pro.ton_*` i18n keys. The 2 historical TON rows in `payment_history` are kept as-is (currency column stays generic; nothing reads them). Env vars `WORDSNAP_TON_WALLET` / `TONAPI_KEY` are now unused — safe to delete from Railway whenever. The [[ton-address-format-trap]] memo stays valid for any future on-chain work. Card + Stars remain the two live lanes.

### Brand positioning

**One-liner:** *"Snap a word from any chat — and the spaced-repetition habit takes care of the rest."*

**Core audience:** Eastern European diaspora (UA / PL relocation, EU students) who already chat in their target language daily but don't formally study. Mini-app meets them where they already are (Telegram), zero install friction.

**Proof points used in copy:**
- 6 supported languages (uk/en/fr/es/pl/de)
- AI-generated examples in target language only (not lazy translation)
- Mastered after 21 days (not arbitrary "level 5")
- $1.49/mo or $8.99/yr — coffee-tier pricing
- Quiz + Spelling drill modes alongside flashcards — varied practice, same SRS scheduler

### Pricing experiments to try
- A/B annual vs monthly default (currently annual)
- Discount tiers from XP ladder are **already configured** but unused — could push them in lifecycle emails

### Metrics that matter (PostHog dashboard "WordSnap Core")
1. Activation funnel: `user_started → ... → review_submitted` (D1)
2. Pro conversion: `pro_page_viewed → buy_clicked → buy_open_attempt → payment_succeeded`
3. Paywall → upgrade: `paywall_hit{daily_limit} → payment_succeeded`
4. Welcome stories: completion vs skip
5. Mode adoption (Cards/Quiz/Spelling)
6. Streak milestones (retention health)

### Economics — costs & revenue (snapshot 2026-05-23)

**Recurring monthly (~$110/mo fixed):**
| Service | $/mo | Note |
|---|---|---|
| **Claude Pro Max** | **$100** | powers Claude Code (dev + Telegram bridge) — 84% of fixed cost; a dev-tooling sub, not WordSnap-runtime |
| Railway | $5 | backend (API + bot + schedulers) |
| ElevenLabs (Starter) | $5 | Reels TTS + music |
| Vercel · Supabase · PostHog · Sentry | $0 | all on free tier (confirmed 2026-05-23) |

**Usage-based API credits (prepaid, pay-as-you-go — separate from Claude Max):**
| Service | Topped up | Used to date | Balance |
|---|---|---|---|
| OpenAI (gpt-4o-mini + Whisper) | $12 | ~$2 | $10 |
| Anthropic API (bots' content gen, now Sonnet 4.6) | $48 | ~$23 | $25 |

The `ANTHROPIC_API_KEY` powers the threads/personal bots' generation; the **Claude Pro Max** subscription powers Claude Code (this repo's dev + the bridge) — two separate Anthropic bills, don't conflate.

**One-time / variable:**
- **Meta Ads: $82.39** lifetime (now paused, $0/day — see ads chronology in §5).
- **TikTok Ads: ~$14** lifetime (582.38 UAH, ad `1866373691040786` v1+v2; KILLED 2026-05-29, 0 signups — see §5).
- **WayForPay: $0 to us** — the 3% fee is surcharged on top of the customer's payment.
- Reddit Ads: $0 (blocked).
- **Supabase Pro $35/mo** (since 2026-06-08): org `kkrluypzbpqryccungow` upgraded after `nghgbxpjqznzjxufkesa` (threads-bot + personal-bot shared project) hit the free-tier 5GB/mo egress cap and started returning HTTP 402 on every PostgREST call (engagement bot broke mid-day). Breakdown: $25 base + $10 Micro Compute for the second project (Pro covers compute for only the first project in the org); $10 Pro compute credit nets one project to $0. Two-project layout kept intentionally — main wordsnap and bot-side data stay isolated, blast radius small. **Open follow-up:** profile egress leak in threads-bot / personal-bot (DB+storage are tiny ~17 MB total — quota burn came from request volume / repeated storage downloads). Pro gives 250 GB egress so we have margin, but worth not wasting it.

**Total cash out to date (~1 month in): ≈ $266** (one-time + Meta + TikTok). **Recurring monthly burn now ≈ $145/mo** ($100 Claude Max + ~$10 Railway/Vercel + $35 Supabase Pro). Stripping the $100 Claude Max dev sub, WordSnap runtime infra is now **~$45/mo + API cents**.

**Revenue (2026-05-23): $4.47/mo** — 3 paying customers × $1.49 monthly Pro (`danishurka`, `luchnykov`, `Альона`). The founder's 2 personal test payments (`payment_history` id 1 & 5, $2.98 total) were excluded from bot revenue stats on 2026-05-23 — status flipped to `excluded_test` (reversible; rows kept for audit; previously inflated gross to $7.45).

**Reality check:** **~$145/mo fixed burn** (since 2026-06-08 Supabase Pro upgrade) vs $4.47 MRR — deeply pre-profitability. Dominated by the $100 Claude Max dev sub; stripping that, actual WordSnap runtime infra is **~$45/mo + API cents** ($35 Supabase Pro + ~$10 Railway/Vercel). The real lever now is acquisition — but paid is now confirmed dead across 5 tests on 2 platforms & 3 destination types (Meta+TikTok, t.me deeplink + /demo gated + /land frictionless, all 0 signups — §5), so the lever is **influencer/affiliate (Rue, Sheku — warm audiences) + organic (threads-bot)** plus the just-shipped tApps Center distribution surface (Phase 1, §5), not more paid spend and not cost-cutting.

---

## 6. Tech architecture (compact)

**API auth (2026-06-24 — security hardening).** Every `/api/*` request must
carry a signed `X-Telegram-Init-Data` header; an HMAC middleware in
`webhook/server.py` validates it (`core/tg_auth.verify_init_data`, key =
`HMAC-SHA256("WebAppData", bot_token)`) and overrides the `telegram_id` query
param with the verified value — so endpoints keep `telegram_id: int =
Query(...)` but the value is trusted. Before this, `telegram_id` was trusted
blindly (anyone could read/modify any account = IDOR). **Public exceptions**
(no auth): `/api/wayforpay/callback` + `/wayforpay/callback` (own signature),
`/api/lead/capture` (anonymous lander), `/pay` + `/health` (not under `/api/`).
**Any new `/api/*` endpoint is authed by default** — add it to
`_PUBLIC_API_PATHS` only if it must be anonymous. **Kill-switch:** set
`REQUIRE_TG_AUTH=0` in Railway env to drop to log-only enforcement if a deploy
locks users out (default on). The mini-app sends the header from
`Telegram.WebApp.initData` (axios interceptor in `miniapp/src/api/client.js`).
Per-word ownership is also enforced in `process_review` (was: any `word_id`).

```
backend/
├── bot/              aiogram handlers (start, words, songs, themes, review).
│                     `bot/instance.py` owns the `Bot` + `Dispatcher` singletons
│                     so FastAPI handlers can `from bot.instance import bot`
│                     without re-executing `bot/main.py` — the process is
│                     launched as `__main__` in prod, so a `from bot.main`
│                     import would re-run the module body and re-attach all
│                     routers (RuntimeError). Touched on 2026-06-08 when the
│                     Stars endpoint surfaced the latent bug; lesson: any new
│                     lazy-import of `bot` must use `bot.instance`, never
│                     `bot.main`.
├── webhook/          FastAPI routes (/api/*, /healthz, /pay, /api/wayforpay/callback)
├── core/             services (openai_client, unsplash_client, srs, rewards,
│                     streaks, referral, avatars, analytics, auto_migrate, ...)
├── scheduler/        4 background loops (reminder, streak_save, recurring_charges, image_backfill)
└── tests/            pytest smoke (i18n, languages, onboarding, rewards, srs)

miniapp/
├── public/           sw.js, onboarding/slide_*.png, icons.svg
├── src/
│   ├── pages/        Home, Words, Review, Stats, Leaderboard, Pro, Settings,
│   │                 Songs, Themes
│   ├── components/   AppBar, NavBar, SnapCard, WordResult, WordDetailModal,
│   │                 SpeakButton, WordPlaceholder, WelcomeStories, Skeleton,
│   │                 ThemeToggle, TierLadder, ExportModal, DebugBanner
│   ├── contexts/     LangContext (i18n)
│   ├── utils/        analytics, optimizeImage, pollImage
│   ├── api/client.js axios + stale-while-revalidate cache
│   └── i18n.js       6-lang dictionary (uk/en/fr/es/pl/de)
└── vite.config.js    manualChunks vendor split (react/router/http/misc)

scripts/
└── setup_posthog_dashboard.py  Auto-builds 8-insight dashboard
```

### Performance characteristics (after May 7, 2026 round)
- First-load: ~120 KB gzip (vendor-react 60 + vendor-router 15 + vendor-http 15 + index 24 + misc 5)
- Repeat-visit re-download: **~24 KB** (only `index.js`)
- `/api/stats` latency: **~50-80 ms** (parallel queries via `asyncio.gather`)
- Words page on user with 50 words: ~2-3 MB image traffic (was ~10 MB before optimization)
- Tab navigation: instant via idle-prefetched lazy chunks

### Operations notes (2026-06-08)
- **Repo public:** `github.com/vzolot/wordsnap` flipped from private to public on 2026-06-08 (secret audit: `.env` was never committed; PostHog `phc_` key embedded in `public/*.html` is the public client-side key, safe). Helps tApps Center credibility + build-in-public posture.
- **Railway CLI is the primary deploy/debug path now.** `railway` linked to `eloquent-serenity / production / worker` (and `wordsnap-personal-bot` / `wordsnap-threads-bot` as sibling services in the same project). Replaces the slow "git push → wait 5-25 min for GitHub auto-deploy → guess from black-box 500s" cycle. Standard ops: `railway logs --build` (build progress live), `railway logs` (runtime tail), `railway redeploy` (force re-deploy without code change), `railway run <cmd>` (one-shot in the prod env). The Stars import RuntimeError on 2026-06-08 took 30 min to debug because we couldn't see logs; the next bug like it should be 2-3 min.
- **Egress optimisation pass (2026-06-08, threads-bot + personal-bot repos):** after the Supabase Pro upgrade ([see §Costs](#costs)), profiled the egress sources on `nghgbxpjqznzjxufkesa` — base+storage were tiny (~17 MB) so the burn was request volume + payload size. Five fixes shipped to those two repos: new `get_approved_posts()` SQL filter (saves ~250 MB/mo on the */30-min publish cron), explicit-column SELECTs replacing `SELECT *` on hot-path reads (~400-500 MB/mo across both bots), an in-process FIFO cache on `RedditListener.reddit_reply_exists` (preventive — saves ~50 GB/mo when Reddit cohort comes back online), and trimmed engagement-bot `get_recent_replies(limit=10→5)` × 6 sites. Net savings ≈ **700-900 MB/mo**, leaving the new Pro 250 GB quota with a >300× safety margin. Open follow-up only if Stars/TON ever materially increase egress.

### Operations notes (2026-06-09 — threads-bot resilience pack)

Diagnosed during the 2026-06-09 audit (triggered when the user noticed the brand IG account had gone quiet): **threads-bot post-daily cron had been silently failing for 16 days**, stacking two distinct root causes on top of each other. (1) **2026-06-03 to 2026-06-08** — Supabase free-tier egress quota hit on the shared `nghgbxpjqznzjxufkesa` project, every PostgREST call returned HTTP 402, pipeline crashed at `get_recent()`. Fixed by the 2026-06-08 evening Supabase Pro upgrade. (2) **2026-06-09** — first manual `workflow_dispatch` after the Supabase fix immediately surfaced a second mode: Claude generated a pillar-post with `body=520 chars` against `PostDraft.body: max_length=500`, pydantic ValidationError, pipeline crashed. Used to be rare because the prompt asks for ≤500, but for pillar-posts aiming near the ceiling Claude occasionally overshoots, and `claude_client.generate()` had no retry loop — a single overshoot dropped the whole day.

Shipped to threads-bot to make this class of failure visible in days not weeks:

- **Claude retry loop (`src/claude_client.py`)** — `generate()` now retries up to 3× on `PostDraft` ValidationError, parses the actual hook/body lengths from the rejected payload and feeds them back to Claude as an `extra_user_hint` ("hook was 234 chars, must be ≤200, trim by 34") so the next attempt is corrective not blind. `meta` payload carries `validation_retries` for analytics.
- **Daily health-check (`scripts/health_check.py` + `.github/workflows/health-check.yml`, daily 09:00 UTC)** — queries the latest `published_at` (or `created_at` for `reels`, which doesn't carry a separate published_at column) on each of `threads_posts` / `instagram_posts` / `reels`. Per-channel staleness thresholds (3-4 days, picked above the planned cadence by ~50% so a single missed cron doesn't false-alarm); fires a Telegram alert to `TELEGRAM_ADMIN_CHAT_ID` when any channel exceeds. Quiet on success. `--always` flag for manual sanity confirms. Caught the IG `cron` failure on first run (5d stale) — system worked exactly as designed.
- **Sentry as second alert channel (`src/sentry_init.py`)** — gracefully no-ops if `SENTRY_DSN` isn't set, otherwise initialises sentry-sdk with traces off + PII off + a `server_name=wordsnap-threads-bot` tag for filtering. `health_check.py` calls `capture_message` right before the Telegram send when stale channels are detected; per-channel `hours_since / threshold / last_at` ride as Sentry extras for debuggable Issue views. Reuses the same `SENTRY_DSN` as the main wordsnap backend for one consolidated dashboard. Set as GH secret on 2026-06-09.
- **Awaiting-drafts digest (`scripts/resend_awaiting.py`)** — recovers drafts stuck in `status='awaiting'` because the original preview message scrolled out of Telegram chat history. One-message-per-draft summary with copy-paste SQL approve/reject one-liners; lighter than spinning up the 30-min approval-bot listener for cleanup. `--channel` filter + `--max-age-days` so ancient dev-relict rows don't get resurrected.
- **IG cron bumped from 5 d/wk to 7 d/wk** (cron `23 17 * * *` since 2026-06-09). IG is the best-converting brand channel and the approval flow handles Sat/Sun identically.
- **WordSnap brand mark unclipped in Reels** — was at Y=REEL_H-180 = 1740 on the 1080×1920 canvas; IG's bottom chrome eats 250-400px so the brand sat half-behind it in-feed. Moved to Y=REEL_H-450 = 1470 (480px clearance). Only affects future renders.

### Operations notes (2026-06-09 — wordsnap UX bug fixes)

Cluster of small bugs the user caught in the same review session, none individually huge but together worth noting since the patterns might repeat:

- **Pro badge inconsistent across pages** — `AppBar` defaulted `isPro={false}` and only Home + Stats passed the real value; Words / Topics / Songs / Review / Leaderboard rendered the pink "Get Pro" CTA even for paying users. Fixed by having AppBar read `stats` from `readCache('stats', { ignoreTtl: true })` directly so every page gets the green PRO badge consistently; explicit prop still wins as override.
- **Stale image flash on Review card swap** — `<img>` element was reconciled across word changes, browser kept serving the old src ~200-500ms until the new download finished. Added `key={current.id}` to each `<img>` to force unmount/remount, plus a `useEffect` that spins up `new Image()` objects for the next 2 words in the queue so the next swap paints from the browser cache on the same frame. Dropped `loading="lazy"` from the review images while we were in there — the user is actively looking at the card, eager-load is correct.
- **`.DS_Store` cleanup** — was tracked in git from the early macOS-only workflow; now public-repo embarrassment. Added to `.gitignore` (plus `*.swp` / `*.swo`) and removed from index.

---

## 7. Where this document lives

**Path:** `/Users/zvuid/Documents/projects/wordsnap/PROJECT.md`
(Repo root, alongside `backend/`, `miniapp/`, `scripts/`.)

Keep this file updated when:
- New page / route is added
- Pricing changes
- A new acquisition channel is launched
- A paid-ads campaign goes live / is killed / scales (update §5 — campaign id, budget, gate outcomes)
- Brand colors / fonts evolve
- A scheduler is added or removed

If a section starts to drift from reality (e.g. a feature gets removed but the doc still mentions it), prefer deletion over a "deprecated" note — code is source of truth.
