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
| Backend (FastAPI + aiogram bot + scheduler) | **Railway** | Yes, on `git push origin main` | One Worker service: API + bot polling + 4 schedulers (reminder, streak-save, recurring-charges, image-backfill) |
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

### 3.6 Pro / monetization

| Plan | Price | Snap limit |
|---|---|---|
| **Trial** (first 7 days) | free | 10 / day |
| **Free** (after trial) | $0 | **3 / rolling 7-day** (freemium tail) |
| **Pro monthly** | $1.49 / mo | 100 / day |
| **Pro annual** | $8.99 / yr | 100 / day |

The free-tier weekly tail (introduced 2026-05-17) replaces the hard 0/day block — keeps the snap habit alive for users who didn't convert in the 7-day trial but might in week 2-4. Counted via `Word.created_at >= now - 7d` (no schema change). Reviews stay unlimited at every tier.

Payment flow: WayForPay HPP via auto-submitted POST form (`/pay` HTML route). Recurring tokens stored after first success.

**Referrals:** Each user has a unique `?start=ref_<code>` link. Both inviter and invitee get **+10 days Pro** stacked on top of trial → effective 17-day trial for referrals. Tracked via `referral_signup` / `referral_completed`.

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
6 languages: 🇺🇦 uk · 🇬🇧 en · 🇫🇷 fr · 🇪🇸 es · 🇵🇱 pl · 🇩🇪 de
- Mini-app: full coverage in `miniapp/src/i18n.js`. French has welcome + nav + common + snap + settings + leaderboard translated; rest falls back to `en`.
- Bot: `backend/core/bot_i18n.py` covers uk/en/es/pl/de fully. French has no bot dict — fallback resolves to `en`.

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
    - **v1 — `WordSnap · Traffic · Validation`** (campaign_id `120247072797960057`, **PAUSED 2026-05-15**). 2026-05-11 → 2026-05-15: OUTCOME_TRAFFIC, $20/day, geo PL/DE/CZ, age 22–45, IG-only, A/B Reel vs static, landing `https://t.me/WordSnapBot/app?startapp=igads_val_2605`. Result after ~$30 spend / 187 link clicks: CPC excellent ($0.16) but **zero attributed `app_opened` events in PostHog** — direct `t.me/...?startapp=...` deeplinks were being dropped inside Meta's in-app browser. Killed against the $80-spend gate early because the funnel below the click was structurally broken.
    - **v2 — `WordSnap · Traffic · Validation v2`** (campaign_id `120247418354910057`, **ACTIVE since 2026-05-15**). Same audience/budget/placements, but landing routed through a Vercel-hosted bridge page: `https://wordsnap-mu.vercel.app/open?ref=igads_val_2605_v2` → fires `landing_visited`, registers PostHog super-props (`acquisition_source=igads` / `acquisition_campaign=val_2605_v2`), then deeplinks into Telegram. PostHog cohort filter: `properties.acquisition_campaign = 'val_2605_v2'`. **Mode: observation, not full-validation.** Burning small test spend to debug the funnel — no fixed $80 gate yet; collecting enough sample (≥50–100 clicks) before any kill/scale call.
    - **Open question (2026-05-16):** v2 funnel reads 21 clicks → 19 `landing_visited` → 8 `tg_app_likely_opened` → only **1** `app_opened` in the SPA. Bridge → Telegram OS handoff seems fine, but Telegram → mini-app SPA load with `start_param` preserved is leaky. Could be sample noise (n=21 is tiny) — pausing the kill decision until more data lands.
    - **Validation gates (apply once v2 has a meaningful sample):** kill if CPC > $1 / mini-app opens < 20% of link clicks / D1 activation < 15%. Scale to Phase 1 ($25–30+/day, geo splits, retargeting) if CPC < $0.40 & D1 activation ≥ 25%.
    - **Meta infra:** Business portfolio `984506147595109`, ad account `act_26992688363704873` (USD), FB Page `1042894552250387`, IG actor `17841408392302831`, system user `wsadsbot`, Meta app `1289392066593154` (now Live, with the "Create & manage ads with Marketing API" use case — same app used for IG/Threads organic). Privacy Policy at `https://wordsnap-mu.vercel.app/privacy.html` (= `/privacy` on the mini-app; `public/privacy.html` in this repo and `miniapp/public/privacy.html`) — registered in the Meta app, was a prerequisite for publishing it Live.

- **Founder account (@vzolottop) — organic, automated.** Threads + Instagram cross-post, first-person Володимир voice, complements the brand reach with a build-in-public arc.
  - *Pipeline:* GitHub Actions cron `daily-content.yml` runs daily at **06:00 UTC (08:00 Kyiv)**: `scripts.content_generator --n 3` (Claude tool-use with validator loop) → `scripts.approve` (Telegram bot **@personal_wsbot**, 30-min decision window, ✅/🔁/❌ per draft) → `scripts.publish --all-approved --platform threads --platform instagram`. Threads gets native text (≤500 chars); IG gets a Pillow-rendered 1080×1350 PNG card (off-white BG, violet→pink gradient strip, Inter Bold body, handle + brand mark + link footer). Per-platform `external_id` dedup means a post can land on Threads later than IG without re-publishing.
  - *5 founder-voice pillars* (`src/prompts/pillars/`): `word_from_life`, `diaspora_pain`, `build_in_public`, `etymology`, `user_stories`. Pillar rotation is target-weighted against recent history (30/20/20/15/15).
  - *Style validator* (`src/content/validator.py`) enforces banned words at generation time — most importantly **«бот» → «додаток» / «Mini App»** (Telegram-spam association), plus «корисний контент», «топовий», «крутий», «залітайте», «друзі». Violations trigger a regen with a hint, up to 3 attempts.
  - *Engagement bot* **@personal_engage_wsbot** — long-running Worker on Railway (separate BotFather token, because Telegram `getUpdates` is exclusive per token, so the cron-time approval bot and this daemon can't share one). Founder sends a **screenshot** of someone's Threads/IG post (optionally with a caption); Claude vision reads the post text from the image and returns a 5-pattern reply (`word_in_context` / `decompose_pain` / `soft_funnel` / `complement` / `sacred_thread`) as a tap-to-copy `<pre><code>` block with ✅/🔁/❌. URL+text fallback also supported. **No auto-publish** — Threads API does not permit `reply_to_id` on other people's posts, so the user pastes the approved reply manually. All replies tracked in `personal_replies` for future self-learning.
  - *Why this matters for §3 acquisition:* founder posts drive **first-person credibility** that the brand account can't replicate. Engagement replies are the channel — they put `t.me/WordSnapBot/app` in front of the exact people who would benefit (someone in a Polish Threads complaining about vocab → context-aware reply with a soft funnel).

### Acquisition surfaces

- **Direct mini-app link** (primary): `https://t.me/WordSnapBot/app` — tap → mini-app opens directly → welcome stories handle full onboarding. This is what the marketing automation publishes / links to. Configured via `/newapp` in BotFather, short_name = `app`. Supports `?startapp=<param>` for campaign attribution (arrives as `start_param` / `tgWebAppStartParam`).
- **Bot chat fallback:** `https://t.me/WordSnapBot` — opens chat with "Open App" launch button.
- **Referral system** — 17-day effective trial via `?start=ref_<code>`. Shareable link in Pro page (uses bot URL, not mini-app URL — old surface, candidate to migrate).
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
