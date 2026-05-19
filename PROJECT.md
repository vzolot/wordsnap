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
| `/songs` | Curated lyric packs (Imagine, Yesterday, Perfect…) — tap a song → see word list → add |
| `/themes` | Curated theme packs (Travel, Food, Office…) — same flow |
| `/stats` | XP card with tier ladder, 6 stat tiles, link to `/leaderboard` |
| `/leaderboard` | Top-50 by total XP, segmented by `target_lang`, your-rank pinned if outside top |
| `/pro` | Subscription card (annual/monthly toggle) + referral block |
| `/settings` | Avatar (32 emojis), native lang, target lang, reminders toggle, leaderboard opt-out, timezone |

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

Payment flow: WayForPay HPP via auto-submitted POST form (`/pay` HTML route). Recurring tokens stored after first success.

**Referrals:** Each user has a unique link. Shareable link generated by `/api/referral` now points at `t.me/<bot>/app?startapp=ref_<code>` — direct mini-app entry, one tap, no intermediate bot chat. The mini-app picks up `start_param`, calls `POST /api/apply_referral` with the code, and the inviter gets a Telegram notification. Old `?start=ref_<code>` links still work via the bot's `/start` handler. Both inviter and invitee get **+10 days Pro** stacked on top of trial → effective 17-day trial for referrals. Tracked via `referral_signup` / `referral_completed`.

### 3.6.1 Affiliate / influencer revenue-share program

Added 2026-05-19. Separate channel from user-to-user referrals — for paid influencer partnerships (Rue and future).

**Mechanics (default Rue terms):**
- Influencer gets a unique `slug` (e.g. `rue`) → trackable deeplink `https://t.me/WordSnapBot/app?startapp=aff_<slug>`.
- New user taps the link → `users.affiliate_slug` + `users.affiliate_at` set on **first touch only** (never overwritten by subsequent ad clicks or other links).
- Every successful payment by that user within `duration_days` of `affiliate_at` generates a row in `affiliate_revenue` with `rev_share_pct` of `payment_amount` as `share_amount`.
- Default terms: **20% × 180 days (6 months)**. Configurable per-influencer.
- Works for both first-time HPP payments (`webhook/api_routes.py` WayForPay callback) AND monthly recurring charges (`scheduler/recurring_charges.py`).
- Idempotent via `payment_id` FK — webhook re-deliveries don't double-credit.

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

**i18n:** `affiliate.welcome` in all 6 langs (e.g. uk: «👋 Привіт! Ви прийшли за порадою <b>Rue</b>. Ласкаво просимо у WordSnap.»). Sent to the user on first `/start aff_<slug>` or on first mini-app entry via direct universal link.

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
    - **Survey funnel results (full v2 window as of 2026-05-18):**
      - `landing_visited` 78 → `landing_survey_lang_picked` **2** (2.6% Q1 conversion) → `landing_survey_motivation_picked` **1** → `app_opened` **2** → `welcome_completed` **0** → `word_added` **0** → `review_submitted` **0** → `payment_succeeded` **0**.
      - Survey on landing has brutal drop-off; most users prefer skipping or bounce entirely.
    - **Validation gates (still pending meaningful sample):** kill if CPC > $1 / mini-app opens < 20% of link clicks / D1 activation < 15%. Scale to Phase 1 ($25-30+/day, geo splits, retargeting) if CPC < $0.40 & D1 activation ≥ 25%.
    - **Current cumulative ad numbers (Meta side, both campaigns):**
      - **Spend $56.24, 268 link clicks, avg CPC $0.21, avg CTR 1.68%.**
      - v1: 187 clicks @ $0.16, CTR 2.33%, $30.42. v2: 81 clicks @ $0.32, CTR 1.23%, $25.82.
      - **Bottom-funnel (both): 78 landing → 61 OS-handoff → 2 SPA → 0 activated → 0 paid.**
    - **Meta infra:** Business portfolio `984506147595109`, ad account `act_26992688363704873` (USD), FB Page `1042894552250387`, IG actor `17841408392302831`, system user `wsadsbot`, Meta app `1289392066593154` (Live, with the "Create & manage ads with Marketing API" use case). Privacy Policy at `https://wordsnap-mu.vercel.app/privacy.html` (= `/privacy` on the mini-app; `public/privacy.html` + `miniapp/public/privacy.html`) — registered in the Meta app, was a prerequisite for publishing it Live.

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
    - **What's pending (needs user action):**
      - Run `supabase/migrations/2026_05_18_reddit_replies.sql` once in the wordsnap-personal-bot Supabase SQL Editor.
      - Build 3 creative posts manually in Reddit Ads UI for v1 (subreddit-targeted), use landing URLs above. Comments **OPEN**.
      - Create Reddit script app at https://reddit.com/prefs/apps → grab `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / set `REDDIT_USERNAME` + `REDDIT_PASSWORD` (the reddit user that owns the ad — replies go from this account) in Railway env for wordsnap-personal-bot.
      - After campaigns go live, copy each ad-post's submission_id from URL → paste comma-separated into `REDDIT_WATCH_SUBMISSIONS` env on Railway. Listener picks up automatically.
      - Future ad-creation automation (`src/reddit_ads_api.py` + CLI in `scripts/ads_pipeline.py`, Supabase `reddit_campaigns` table) — defer until first manual campaign proves the channel; mirroring existing `meta_ads_api.py` pattern is straightforward when API access is ready.
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

---

## 6. Tech architecture (compact)

```
backend/
├── bot/              aiogram handlers (start, words, songs, themes, review)
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
