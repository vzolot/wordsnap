# WordSnap — Project Overview

> Snap a word from any chat → spaced repetition does the rest.
> Telegram Mini App for the Eastern European diaspora learning languages.

**Stack:** FastAPI (Python 3.12) + React 19 (Vite) · Supabase Postgres · Railway + Vercel
**Status:** Production. ~10-day streak users, real payments, Sentry-quiet.
**Last major release:** 2026-05-08 (welcome onboarding + 6 langs + perceived-perf round)
**Bot:** [@WordSnapBot](https://t.me/WordSnapBot) · **Mini-app URL:** https://miniapp-omega-three.vercel.app

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
| Errors | **Sentry** | Auto | Backend + frontend. Quiet 24h+ as of 2026-05-07. |
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

### 3.3 Onboarding stories
3 swipeable slides shown on first open. Photo + DOM-overlay chips. Skip button + step CTAs. All steps tracked in PostHog (`welcome_step_viewed{n}`).

### 3.4 Spaced repetition
- SM-2 algorithm (`backend/core/srs.py`)
- `LEARNING_THRESHOLD = 21` days → `mastered`
- Quality 1/3/5 maps to forgot/struggled/knew → 2/6/10 XP
- Daily push picks the most-overdue learning word

### 3.5 Word of the Day push
- Scheduler runs every 60s
- Sends one word per local day at user's `reminder_time` (default 09:00 in their `timezone`)
- Anti-spam: `users.last_daily_push_date` (one per local day)
- Stamp date even if no due word so re-checks don't repeat

### 3.6 Pro / monetization

| Plan | Price | Daily snap limit |
|---|---|---|
| **Trial** (first 7 days) | free | 10 / day |
| **Free** (after trial) | $0 | 0 / day (read-only) |
| **Pro monthly** | $1.49 / mo | 100 / day |
| **Pro annual** | $8.99 / yr | 100 / day |

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
5 languages: 🇺🇦 uk · 🇬🇧 en · 🇪🇸 es · 🇵🇱 pl · 🇩🇪 de
Both bot copy (`backend/core/bot_i18n.py`) and mini-app copy (`miniapp/src/i18n.js`).

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

### Logo

Square gradient tile with white "W" letterform. Used as bot avatar, mini-app `app-bar-logo`, share OG image.

---

## 5. Marketing

### Active channels

- **Threads (automated)** — daily posts via [vova-bot/wordsnap-threads-bot](https://github.com/vova-bot/wordsnap-threads-bot) (separate repo). Pulls product moments + screenshots, generates copy, queues at scheduled times. Currently the only paid acquisition channel.

### Acquisition surfaces (built but not actively pushed)

- **Referral system** — 17-day effective trial via `?start=ref_<code>`. Sharable link in Pro page.
- **Telegram bot username** — direct discoverability.
- **Onboarding stories** with embedded "+10 days Pro" CTA on slide 3.

### Brand positioning

**One-liner:** *"Snap a word from any chat — and the spaced-repetition habit takes care of the rest."*

**Core audience:** Eastern European diaspora (UA / PL relocation, EU students) who already chat in their target language daily but don't formally study. Mini-app meets them where they already are (Telegram), zero install friction.

**Proof points used in copy:**
- 5 supported languages (uk/en/es/pl/de)
- AI-generated examples in target language only (not lazy translation)
- Mastered after 21 days (not arbitrary "level 5")
- $1.49/mo or $8.99/yr — coffee-tier pricing

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
│   └── i18n.js       5-lang dictionary
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
- Brand colors / fonts evolve
- A scheduler is added or removed

If a section starts to drift from reality (e.g. a feature gets removed but the doc still mentions it), prefer deletion over a "deprecated" note — code is source of truth.
