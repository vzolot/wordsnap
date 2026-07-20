# Session log — 2026-07-20

Повний перелік зробленого за сесію по всій екосистемі WordSnap
(мініап + бекенд, лендинг, соц-автопостинг). Усе — в проді, якщо не позначено інше.

Репозиторії:
- `wordsnap` — мініап (Vercel) + бекенд/бот (Railway) + БД (Supabase)
- `wordsnap-landing` — маркетинговий лендинг (Vercel, домен `wordsnap.app`)
- `wordsnap-threads-bot` — соц-автопостинг (@wordsnapapp + B2B-кампанія на @vzolottop)
- `wordsnap-personal-bot` — консюмерський автопостинг на @vzolottop (ВИМКНЕНО)

---

## 1. Мініап + бекенд (`wordsnap`)

### Викладацький кабінет — фікси й фічі
- **Видалення учня** (Марта / викладач школи / адмін): `DELETE /api/teacher/students/{id}`
  + `group_service.remove_student`. У статистиці видалення тепер **перезавантажує
  список** (учень зникає з KPI та списку одразу).
- **Статистика по словах/фразах** учня: `teacher_stats.student_detail` повертає
  `words[]` зі `strength` (сильне/вчиться/слабке), секція «Слова та фрази».
- **Видалення викладачів адміном**: `DELETE /api/teacher/teachers/{id}` +
  `group_service.remove_teacher` (прибирає групи/колоди/уроки викладача, учнів
  лишає в школі), кнопка 🗑 у SchoolManager.
- **Фікс оплати Марти** (регресія): у не-шкільному тенанті оплату видно завжди;
  у школі — лише owner/адмін (`showBilling = is_school ? owner&!ownerAsTeacher : true`).
- **«бот» → «застосунок»** у всіх рядках.
- **Групова колода показує реальну к-ть учнів** (членів групи), а не «0»
  (`list_teacher_decks`: для `group_id` рахуємо `GroupMember`).

### Повна локалізація кабінету на 6 мов (en/uk/es/pl/de/fr)
- ~170 ключів `teacher.*` × 6 мов у `miniapp/src/i18n.js` (+ `nav.lessons`).
- Рефакторинг усього `TeacherPage.jsx` (15 компонентів, 171 виклик `t()`),
  `NavBar.jsx` (вкладки), `AppBar.jsx` (aria-label).
- Fallback `dict[key] ?? T.en[key] ?? key` — відсутні падають на англійську.
- Довгі тире (—) → короткі (–) по всьому UI мініапу (304 заміни).

### Онбординг
- Перероблено в **темну тему сайту** (фон #0C0D12 + фіолет→лаванда сяйво,
  бейджі/SRS у #7C6CFF→#A78BFA, амбер-CTA, заголовки Unbounded). Додано
  `@fontsource/unbounded`.
- Фікс: у режимі «як учень» показуємо **учнівський** онборд (`teacherMode`
  замість `isTeacher` у `slidesFor`).

### Демо-флоу (`/start` у демо-ботах Марта t2 / Мовна школа t3)
- **Вибір мови застосунку з 6 мов** перед відкриттям (🇺🇦🇬🇧🇪🇸🇵🇱🇩🇪🇫🇷),
  далі — **покрокова інструкція «як тестити»** тією ж мовою (× викладач/адмін,
  усі 12 варіантів). `set_native_lang_explicit()` — легкий хелпер (лише UI-мова).
- **Мова через `?lang=` в URL**: кнопка «Відкрити застосунок» веде на
  `MINI_APP_URL?lang=<code>`; app (`getInitialLang`) читає її з НАЙВИЩИМ
  пріоритетом (перекриває застарілий локальний вибір). Виправляє «обрав
  English — а кабінет українською».
- **Наповнений викладацький бік у школі**: `demo_seeded_owner_id()` — демо-
  проспект-власник у режимі «як викладач» бачить дані посіяного власника
  (не порожньо); інжект у `_school_scope` (учні/колоди) + `_target_teacher`
  (календар). Сід власника школи збагачено: **5 учнів + 2 колоди + розклад Пн–Пт**.
- **Двомовний опис ботів** (`bot_menu.py`): дефолт — укр+англ; en-клієнт — чистий англ.
- Назви демо-колод: «Демо:» → **«Demo:»** (латиниця читається всіма мовами;
  `cleanup` прибирає обидва префікси).

### Конверсійний «міст» після демо
- `scheduler/demo_conversion.py`: проспект, що відкрив демо й отримав викладацький
  доступ, за ~4 хв отримує від бренд-бота пітч «хочете такий застосунок під ваш
  бренд?» з кнопкою на Instagram (@vzolottop). Раз на проспекта
  (колонка `users.demo_pitch_sent`). Реального власника не чіпає.

### Аватарка школи
- Підтягнув аватар @language_schoolbot з Telegram → `tenants.logo_url` (t3).

### Продуктивність / UX
- **Boot-loader** у `index.html` (брендований W у темі Telegram) — миттєвий екран
  замість кількох секунд порожнечі, поки вантажиться JS-бандл.
- **Безшовне завантаження**: Suspense-fallback `RouteFallback` тепер = той самий
  W-лоадер (не «різні екрани»: boot → Suspense → сторінка виглядає одним завантаженням).

### Демо-сід (`seed_demo.py`)
- Ідемпотентне наповнення t2/t3: учні з прогресом, викладачі, колоди (слова+фрази),
  розклади (варіативні per-teacher), уроки, мовні бейджі, кілька «struggled» рев'ю
  (слабкі слова), група власника школи. Запуск: `cd backend && railway run .venv/bin/python seed_demo.py`.

---

## 2. Лендинг (`wordsnap-landing`, `wordsnap.app`)

### Домен + SEO (закрито повністю)
- Підключено власний домен **`wordsnap.app`** (Namecheap DNS: A `76.76.21.21`
  + CNAME `www → cname.vercel-dns.com`), HTTPS.
- **Пре-рендер тіла**: `prerender.mjs` (Playwright + системний Chrome) робить
  статичний знімок SPA в `index.html` → краулери/no-JS бачать повний контент.
  Пайплайн деплою: `vercel build → node prerender.mjs .vercel/output/static →
  vercel deploy --prebuilt --prod`.
- Статичні **meta/OG/Twitter** + `canonical` + **OG-зображення 1200×630**
  (`creatives/og-render.mjs` → `public/og.png`).
- **robots.txt** + **sitemap.xml**.
- **Google Search Console**: верифіковано (HTML-файл), sitemap подано,
  **сторінку проіндексовано** ✅.
- **Vercel Web Analytics** — код (`<Analytics/>`) задеплоєно; лишилось увімкнути
  в дашборді (Analytics → Enable) ⏳.

### Дизайн/контент
- Преміум-редизайн (темна тема, скло, Unbounded+Golos, lucide-іконки).
- Ціни без плашок «Рекомендуємо»/«PRO», картки вирівняні, хук «місячна вартість
  — як ціна одного уроку», термін «за добу» скрізь уніфіковано.
- FAQ: прибрано дублі, додано «Що буде з учнями, якщо скасую підписку?».
- Фікси: FAQ-акордеон (зникало питання), виділення слів (без налізання),
  мобільна шапка (CTA не влазив), картки-рішення 2×2, порядок секцій
  (демо після проблеми), en-dashes, аватар «Мовна школа».

---

## 3. B2B-кампанія в Instagram/Threads (`wordsnap-threads-bot`)

- **15 креативів** у дизайн-системі лендингу (1080×1080, `creatives/posts.js`
  + `render.mjs` — HTML→PNG через Playwright, шрифти Unbounded+Golos inline).
  3 пости/день × 5 днів.
- `scripts/campaign_pipeline.py` — постить наступні N креативів через
  Telegram-підтвердження (@ig_wsbot), стан у `.campaign_state.json`.
- `scripts/threads_dup_pipeline.py` — дзеркалить опубліковані в IG на **Threads**
  @vzolottop (додано `ThreadsClient.post_image`).
- Постить на **@vzolottop** (окремі креденшели `CAMPAIGN_IG_*` / `CAMPAIGN_THREADS_*`,
  щоб не чіпати консюмерський @wordsnapapp-пайплайн).
- **Стан: 9/15** (Дні 1–3 в IG+Threads). Лишилось Дні 4–5 (6 постів).

---

## 4. Консюмерський автопостинг вимкнено (`wordsnap-personal-bot`)

- «Словникові» пости (діаспора/етимологія) на особистий @vzolottop **зупинено**:
  `gh workflow disable daily-content.yml` + `publish-approved.yml`
  (обидва `disabled_manually`; re-enable через `gh workflow enable`).
- Старі опубліковані пости (171: ~168 IG, ~153 Threads) **видалити через API не
  можна** (IG не підтримує; Threads — бракує дозволу `threads_delete`). Лишили.

---

## Відкриті пункти
1. **Vercel Analytics** — увімкнути в дашборді (1 тап).
2. **Кампанія Дні 4–5** — 6 постів (запустити `campaign_pipeline` + `threads_dup`).
3. **Старі пости @vzolottop** — API-видалення заблоковане; лишили / Threads за
   потреби з токеном `threads_delete`.

## Ключові команди
- Демо-сід: `cd backend && railway run .venv/bin/python seed_demo.py`
- Деплой лендингу (з пре-рендером): `cd wordsnap-landing && vercel build --prod &&
  node prerender.mjs .vercel/output/static && vercel deploy --prebuilt --prod`
- Кампанія: `cd wordsnap-threads-bot && DRY_RUN=false CAMPAIGN_BATCH=3
  CAMPAIGN_DIR=.../wordsnap-landing/creatives .venv/bin/python -m scripts.campaign_pipeline`
  → потім `... -m scripts.threads_dup_pipeline`
