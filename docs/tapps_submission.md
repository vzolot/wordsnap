# tApps Center submission — WordSnap

Підготовка до подачі WordSnap у [tApps Center](https://t.me/tapps_bot) та запиту на feature/banner. Кодова частина (Фаза 1) уже в коді й чекає деплою; решта — ручні кроки.

## Що вже зроблено в коді (цей PR)

- **EN-onboarding link** — `t.me/WordSnapBot?start=tapps` (бот) і `t.me/WordSnapBot/app?startapp=tapps` (direct mini-app) тепер форсять англійський онбординг і записують `acquisition_payload="tapps[...]"` для cohort-аналізу.
- **Telegram Stars** як додаткова оплата (карта залишається основною). 99 ★ / місяць, 599 ★ / рік. Разова оплата (без recurring).
- **`@telegram-apps/analytics` SDK** інтегровано в `miniapp/src/main.jsx` (init guarded на `VITE_TG_ANALYTICS_TOKEN`).
- **Standards compliance:** `tg.ready()`, `tg.expand()`, native `BackButton` на підсторінках, `setHeaderColor`/`setBackgroundColor` синк, `disableVerticalSwipes`, `enableClosingConfirmation`, theme auto-detect.

## Ручні кроки (порядок)

### 1. Зареєструвати мініапу в `@DataChief_bot` (Telegram)

```
/start у @DataChief_bot
→ "Add app" → бот: @WordSnapBot → app name: wordsnap
→ отримуєш `analytics token`
```

Зберегти token у Vercel env:

```bash
# у Vercel CLI або UI
vercel env add VITE_TG_ANALYTICS_TOKEN production
# вставити token, потім redeploy miniapp
```

Без цього кроку SDK не запуститься (init guarded, не падає, але й даних нема — а tApps вимагає).

### 2. Подати мініапу в `@tapps_bot` (listing)

```
/start у @tapps_bot
→ "Submit your app"
```

Дані заявки:
- **App name:** WordSnap
- **Bot:** @WordSnapBot
- **Mini-app URL:** `https://miniapp-omega-three.vercel.app` (або кастомний домен якщо буде)
- **Category:** Education / Languages
- **Short description (≤80 chars):**
  > Learn words you actually meet — spaced repetition for real-life vocab.
- **Long description (EN, ≤500 chars):**
  > WordSnap helps you build real vocabulary by snapping words from chats, books, or anywhere you read. Spaced-repetition reviews lock them in, daily streaks keep you going. Supports Polish, German, Spanish, French, English & Ukrainian. Free trial, no card needed — pay with card or Telegram Stars.
- **Supported languages:** EN, UK, PL, DE, ES, FR
- **Web3 / TON:** **NO** (Web2, ask for editorial discretion in cover letter — see template нижче)

### 3. Підготувати скріншоти (потрібно 4-6 шт., 1080×1920 portrait)

Бажано зробити мобільні скріни мініапи в Telegram-iOS / Android:

1. **Home page** — стрімкий заголовок, статистика streak/words
2. **Add word** — момент додавання нового слова (Polish/English example)
3. **Review (cards)** — флешкарта в процесі повтору
4. **Stats / progress** — графік прогресу, leaderboard
5. **Pro page** — Stars + card payment options (показати обидва)
6. (Optional) **Settings / multi-lang** — щоб видно було, що app працює зі 6 мовами

Зберегти у `docs/tapps_screenshots/` (створи папку коли робитимеш) у форматі `01_home.png`, `02_add_word.png` тощо.

### 4. Cover letter для editorial team (Web2 discretion)

Оскільки WordSnap — Web2 без TON, варто разом із заявкою надіслати лист (через @tapps_bot або email на tappscenter@telegram, якщо буде в правилах) із обґрунтуванням:

```
Hi tApps team,

WordSnap is a Web2 educational mini-app that helps people learn real-life
vocabulary in 6 languages (EN, UK, PL, DE, ES, FR). We hit ~74 users in 30
days organically with 540+ reviews/week — a small but very engaged core.

We don't run on TON yet, but per your rules ("Publishing posts about web2
TMA … remains at the discretion of the tApps Center's editorial team")
we'd love to be considered for feature/banner placement.

What we offer beyond a typical web2 TMA:
• Telegram Stars payments (primary card + Stars secondary)
• Full @telegram-apps/analytics SDK integration
• Native Standards compliance (BackButton, theme sync, closing
  confirmation, no vertical-swipe-close)
• 6-language UI auto-detected from Telegram language_code
• Clean tapps-cohort attribution so we can measure how the feature
  performed for you

We'd love a slot. Roadmap-wise, if traction from tApps justifies it,
TON integration is our next concrete step.

— Volodymyr (founder, @vzolot)
```

### 5. Дотриматись 7-working-days lead-time

Правило: запит мінімум за 7 робочих днів. Якщо хочеш публікації в робочий тиждень — подати **до вечора четверга попереднього тижня**. Спланувати дату публікації наперед і подати з запасом.

### 6. Після успішного listing

- Зміни canonical share-link на `https://t.me/WordSnapBot?start=tapps` (EN-онбординг) для всіх tApps-cовнішніх місць
- Через тиждень глянути PostHog cohort `acquisition_payload LIKE 'tapps%'` та `app_opened` з last_touch_source='tapps' — це покаже, скільки реально юзерів прийшло
- Якщо traffic значущий, але feature/banner не дають — варто рознайти TON Connect (Фаза 2)

## Validation gates після публікації

- Якщо feature дає **≥50 нових юзерів** із tApps cohort за тиждень → канал перевірений, продовжуємо просити feature
- Якщо **<10** → editorial discretion обмежений; готуємо TON інтеграцію як Фазу 2 для гарантованої eligibility
- Якщо Stars-конверсія **>2×** card-конверсії → ставимо Stars як головну CTA, карту — як secondary

## Документи й посилання

- Правила: https://t.me/tapps_bot (FAQ всередині бота)
- Analytics SDK: https://github.com/Telegram-Mini-Apps/analytics
- Standards & Best Practices: https://docs.telegram-mini-apps.com / Telegram Mini Apps documentation
- Наша атрибуція tApps: `acquisition_payload LIKE 'tapps%'` у `users`, та startapp-параметр `tapps`/`tapps_<sub>`
