# WordSnap White-Label — журнал реалізації

Перетворення WordSnap на мультитенантну платформу для викладачів мов.
ТЗ: `TZ_WordSnap_WhiteLabel_v1.md`. Кожен milestone — окремий коміт/PR.

## Важливі уточнення до ТЗ (реальність кодбейсу ≠ припущення ТЗ)

ТЗ писалось із кількома неточними припущеннями. Фактичний стан:

| ТЗ каже | Реальність | Наслідок |
|---|---|---|
| PostgreSQL на **Railway** | PostgreSQL на **Supabase** (pooler, RLS увімкнено) | Міграції мусять вмикати RLS на нових таблицях (як решта схеми) |
| Міграції через **Alembic** | Ідемпотентні SQL у `core/auto_migrate.py`, що біжать на кожному старті | Нову схему додаємо туди ж, не Alembic |
| Бот на **вебхуках** `/webhook/{id}` | Бот на **long-polling** (`dp.start_polling`) | M2: мультибот через `dp.start_polling(*bots)`, а не вебхуки — безпечніше для живого прода |
| Є таблиця **decks** | Слів немає окремих колод: `words` належать напряму юзеру, SRS-стан на рядку слова | Вводимо колоди як шаблон (`decks`+`deck_words`), учням матеріалізуємо у `words` |

Решта архітектури ТЗ лишається як є: один кодбейс/деплой/БД, ізоляція через
`tenant_id`, тенант id=1 = базовий WordSnap.

---

## M1 — Схема БД + tenant за замовчуванням ✅

**Модель даних (нове):**
- `tenants` — бренд/бот/налаштування тенанта. Тенант id=1 = `wordsnap`
  (billing_ui увімкнено, `ai_snap_monthly_limit=NULL` → без ліміту).
  `bot_token` — секрет (RLS + ніколи не логуємо/не віддаємо в API).
- `ai_snap_usage (tenant_id, month 'YYYY-MM', count)` — лічильник AI-снапів/міс.
- `decks` — колода-шаблон викладача (`assign_to_all`, `owner_user_id`, `tenant_id`).
- `deck_words` — слова-шаблони колоди (без SRS-стану).
- `deck_assignments (deck_id, user_id)` — персональні призначення (коли `assign_to_all=false`).

**Зміни в існуючих таблицях:**
- `users`: `+tenant_id (NOT NULL DEFAULT 1, FK)`, `+role ('student'/'teacher'/'owner')`,
  знято single-column UNIQUE з `telegram_id`, додано UNIQUE `(telegram_id, tenant_id)`.
  → Один учень може існувати незалежно в кількох тенантів.
- `words`: `+tenant_id (DEFAULT 1, FK)`, `+deck_id (nullable FK→decks)`. Слово,
  матеріалізоване з колоди викладача, має `deck_id`; особисте слово учня — NULL.
- `reviews`: `+tenant_id (DEFAULT 1, FK)`.

**Дизайн колод (ключове рішення):** `words` лишається носієм SRS-стану на учня.
Колода викладача — це шаблон (`deck_words`); при призначенні учню слова
матеріалізуються рядками в `words` (`deck_id` заповнено). Так уся наявна механіка
SRS / review / нагадувань працює без переписування. Матеріалізація — у M5.

**Backward-compat:** усі нові колонки з `DEFAULT 1`, тож старий код, що вставляє
`users/words/reviews` без `tenant_id`, продовжує писати в тенант 1. DEFAULT
приберемо в M4, коли весь код стане tenant-aware.

**Тест:** `scratchpad/test_m1_migration.py` — прогін реального списку `MIGRATIONS`
на локальному Postgres поверх симульованої дореформеної схеми з даними. Перевіряє:
ідемпотентність (2 проходи, 0 помилок), backfill у тенант 1, зняття старого
unique, композитний unique, наявність нових таблиць, bump sequence, інваріант
ізоляції (той самий telegram_id у 2 тенантів OK; дубль `(telegram_id, tenant_id)`
відхилено). Статус: **PASSED**. Наявні 124 логічні тести — без регресій.

**Деплой:** Railway автодеплой з підключеної гілки. Міграції виконуються
автоматично на старті (`run_auto_migrations` у `bot/main.py`). Перед мержем у
прод-гілку — зробити бекап: `pg_dump "$DATABASE_URL" > backup_pre_m1.sql`.

---

## M2 — Мультибот (polling) ✅

**Рішення транспорту:** бот WordSnap живе на long-polling, не вебхуках. Для
мультибота обрано **polling для всіх ботів** (узгоджено з оператором) —
`dp.start_polling(*усі_боти)`, один спільний диспетчер. Не чіпаємо перевірений
транспорт живого бота; вебхук-міграція живого прода відкинута як ризикована.

**Нове:**
- `core/tenant_service.py` — резолв тенантів, `parse_bot_id`, `sync_default_tenant`
  (заповнює тенанту 1 `bot_token`/`bot_id` з env `TELEGRAM_BOT_TOKEN`),
  `get_active_tenants`, `create_tenant`, резолв за bot_id/slug.
- `core/bot_registry.py` — реєстр Bot-інстансів: `tenant_id ↔ Bot`, і
  `bot.id → tenant_id` (щоб хендлер знав свій тенант). Невідомий бот → фолбек 1.
- `scripts/add_tenant.py` — admin-скрипт: `--slug --display-name --bot-token
  --owner-telegram-id [--logo-url --color-* --plan]`. Валідує токен через getMe,
  парсить bot_id, створює тенант, друкує Mini App URL для BotFather-меню.
  bot_token НЕ друкується. Нагадує: **Railway Redeploy** щоб бот піднявся.

**Startup (`bot/main.py`):** після міграцій — `sync_default_tenant()`, реєстрація
головного бота як тенанта 1 (та сама сесія, без 2-ї сесії на той самий токен),
підняття ботів активних тенантів, `delete_webhook` на кожному, `start_polling(*боти)`.

**Хендлери:** aiogram передає в хендлер той `bot`, що прийняв апдейт, тож
`message.answer()` автоматично відповідає з правильного бота тенанта. Проактивні
відправлення (шедулери) поки шлють з тенанта 1 — рефактор у M4.

**Додавання тенанта = restart:** новий бот підхоплюється при старті процесу.
Оператор після `add_tenant.py` тисне Railway Redeploy. Прийнятно для оператор-
кер. продукту (<20 ботів на акаунт BotFather).

**Тест:** `scratchpad/test_m2.py` — parse_bot_id, create_tenant (bot_id парсинг,
billing_ui=false для white-label, кастомні кольори), get_active_tenants виключає
paused, резолв за bot_id/slug, registry Bot↔tenant + фолбек. Статус: **PASSED**.

---

## M3 — Резолв тенанта в Mini App + брендинг ✅

**Бекенд:**
- `core/tg_auth.py`: `resolve_init_data()` — перевіряє підпис initData проти
  токена КОЖНОГО зареєстрованого бота; збіг визначає тенант. Повертає
  `(tenant_id, telegram_id)`. **Безпека:** tenant_id не від клієнта, а з того,
  чиїм ботом підписано initData — підробити чужий підпис без токена неможливо.
- `webhook/server.py` middleware: підставляє перевірені `telegram_id` І
  `tenant_id` у query (override клієнтських значень); клієнт tenant_id не контролює.
- `GET /api/tenant/config` → `{display_name, logo_url, color_primary, color_accent,
  ai_snap_available, billing_ui_enabled}`. `ai_snap_available` рахується з
  `ai_snap_usage` за місяць vs `ai_snap_monthly_limit` (NULL=без ліміту). bot_token
  НІКОЛИ не віддається.
- `tenant_service`: `get_ai_snap_count`, `ai_snap_available`, `incr_ai_snap_usage`
  (атомарний upsert), `config_payload`.

**Фронтенд (`miniapp`):**
- `contexts/TenantContext.jsx` — тягне config на старті (+localStorage-кеш для
  миттєвого бренду), застосовує кольори бренду як CSS-змінні (`--violet`, `--pink`,
  `--gradient` + похідні soft/dark), віддає `billingEnabled`/`aiSnapAvailable`/бренд.
- `App.jsx`: `TenantProvider` навколо застосунку; маршрут `/pro` існує ЛИШЕ коли
  `billingEnabled` (white-label → перехід на /pro редіректить на home, цін немає).
- `AppBar.jsx`: назва/лого з бренду тенанта; Pro-CTA прихований для white-label.

Для тенанта id=1 config повертає дефолтний бренд і billing=true → WordSnap
візуально й функціонально не змінюється.

**Тест:** `scratchpad/test_m3.py` — валідний initData кожного бота → правильний
tenant; той самий user id через різні боти → різні тенанти (ізоляція); tampered/
forged initData → None (не підробити чужий тенант); config ховає білінг для
white-label, бренд правильний, bot_token не тече; ліміт AI-снапу (29/30 ok, 30/30
блок). Фронт `npm run build` — OK. Наявні 124 тести — без регресій. **PASSED**.

**Лишок для M4:** hardcoded hex-кольори (5 місць у App.css) не підхоплюють
brand-override; софт-повідомлення «фото/войс доступні з наступного місяця» —
бот-сайд (snap_handler tenant-aware + перевірка ліміту). Скоупінг усіх запитів
по tenant_id — весь M4.

---

## M4 — Скоупінг усіх запитів по tenant_id + ізоляція ✅

Найважливіший milestone для коректності: `telegram_id` більше НЕ унікальний
ключ — усе резолвиться по парі (telegram_id, tenant_id).

**Сервіси:**
- `user_service.get_or_create_user(..., tenant_id=1)` — резолв/створення в межах
  тенанта. `referral_code` лише для тенанта 1 (детермінований+UNIQUE — інакше
  конфлікт). `increment_word_counter`, `update_user_languages`,
  `disable_reminders_if_blocked` — теж tenant-scoped.
- `can_add_word`: white-label тенанти (≠1) — БЕЗ лімітів (білінг прихований).
- `word_service.save_word(..., tenant_id, deck_id)` — стемпить tenant на слові;
  `process_review` стемпить `Review.tenant_id` зі слова.
- `deck_service.get_visible_decks(user_id, tenant_id)` — інваріант видимості
  колод (тенант + assign_to_all|персональне призначення).

**API (`api_routes.py`):** `_get_user(session, telegram_id, tenant_id)` + КОЖЕН
ендпоінт приймає `tenant_id: int = Query(1)` (підставляє middleware з підпису —
клієнт не контролює) і передає далі. Leaderboard фільтрується по tenant_id.
Реферали/сабскрайб — no-op для не-WordSnap. Платіжний callback лишається тенант-1.

**Бот-хендлери:** усі 6 файлів (`main.py`, word/review/setup/snap/songs) деривлять
`tid = tenant_id_for_bot(message.bot|callback.bot)` і передають у
get_or_create_user/save_word/increment/update_languages + tenant-фільтр на прямих
User-апдейтах. (survey/admin — тенант-1 flows, лишені за замовч.)

**Шедулери:** `reminder`, `reengage`, `streak_save` шлють кожному юзеру з бота
ЙОГО тенанта (`bot_registry.get_bot(user.tenant_id)`, фолбек тенант 1).
`telegram_send.send_message/send_document(..., tenant_id)` резолвить токен бота
тенанта. `admin_report` скоуплено до тенанта 1 (WordSnap-аналітика не забруднюється).

**Тести ізоляції (`tests/test_isolation.py`, gated на TEST_DATABASE_URL):**
(а) учень тенанта A не бачить колод B; (б) учень X не бачить персональних колод
Y всередині тенанта; + скоуп user-резолву, words/reviews, leaderboard,
save_word.tenant_id, безлімітність white-label. **PASSED.** Наявні 124 логічні
тести — без регресій (разом 125).

**Ще відкрито (не блокує):** бот-review flow викликає `process_review` без
`user_id`-гейта (не крос-тенант leak — word_id це унікальний PK; захист-в-глибину
можна додати). Hardcoded hex у App.css. Софт-повідомлення ліміту AI-снапу в боті —
разом з M11 (снап викладача).

---

## M5 — Режим викладача в Mini App ✅

**Бекенд (`core/deck_service.py` + `webhook/teacher_routes.py`):**
- `parse_word_pairs` — толерантний парсер «слово - переклад» (тире/em-dash/двокрапка
  з пробілами), таб, `;`, `,` (CSV); дедуп, пропуск сміття.
- `create_deck` — колода + `deck_words` + призначення + **матеріалізація** слів
  адресатам (усім студентам тенанта / обраним). Адресати валідуються по тенанту.
- `add_words_to_deck` — дописує слова і матеріалізує ЛИШЕ нові (ON CONFLICT DO
  NOTHING по (user_id, word, target_lang)) → **старий прогрес не скидається**.
- `remove_deck_word`, `set_deck_assignees` (перепризначення + матеріалізація нових).
- `sync_decks_for_user` — ленива матеріалізація на завантаженні words/review;
  новий учень так підхоплює assign_to_all-колоди.
- `list_teacher_decks` / `get_deck_detail` / `list_tenant_students` (імʼя =
  first_name + @username).
- Ендпоінти `/api/teacher/*` під initData-middleware + `_require_teacher`
  (role teacher/owner + збіг тенанта, інакше 403).

**Фронтенд:** `pages/TeacherPage.jsx` — список колод, форма створення (назва +
textarea пар + «Всім / Обраним» + чекбокси учнів), редагування (список слів з
видаленням, дописування, повідомлення про збереження прогресу). `NavBar` показує
вкладку «Викладач» лише коли `role∈{teacher,owner}` (з кешу stats; `/api/stats`
тепер віддає `role`). Маршрут `/teacher` у `App.jsx`. Текст — українською.

**Критерій (перевірено):** викладач вставляє 15 слів, обирає одного учня → лише
він бачить колоду й отримує слова; викладач дописує 5 → учень бачить 20, старий
прогрес збережено. Крос-тенант адресати ігноруються.

**Тести:** `scratchpad/test_m5.py` (повний флоу) + repo `tests/test_teacher_decks.py`
(парсинг, матеріалізація, no-reset, ізоляція) — gated на TEST_DATABASE_URL.
Разом **127 тестів PASSED**. `npm run build` OK.

**Відкрито:** нагадування учню про призначення колоди (нотифікація) — M5 критерій
згадує «отримує нотифікацію»; зараз слова зʼявляються при відкритті. Пуш про нову
колоду можна додати (шле бот тенанта) — невеликий доробок, зробити з M10-дайджестом.

---

## M6 — Дашборд прогресу для викладача ✅

**Бекенд (`core/teacher_stats.py`):** усе bulk-запитами (без N+1), у межах тенанта.
- `students_overview(tenant_id)` — стрік, повторень за 7д, останній візит,
  % вивчених слів з колод викладача, прапор `at_risk` (≥5 днів без візиту).
  Сортування: неактивні зверху (кому написати). Містить id+display_name → годиться
  і як пікер адресатів у формі створення колоди.
- `student_detail(tenant_id, user_id)` — стрік, активність 7/30д (по днях),
  прогрес по кожній колоді (learned/in_progress/not_started), топ-10 «слабких
  слів» за часткою помилок (forgot+struggled)/total, min 3 повторення.
- Ендпоінти `GET /api/teacher/students` (агрегати) + `GET /api/teacher/students/{id}`
  (деталі), обидва під `_require_teacher`.

**Фронтенд:** сегмент-перемикач «Колоди / Учні» у `TeacherPage`. Список учнів
(стрік 🔥, 7д, %вивчено, relative last-visit, бейдж «в ризику»). Детальний екран:
метрики, спарклайн активності 30д, прогрес-бари по колодах (learned/in-progress),
слабкі слова з % помилок.

**Критерій (перевірено):** overview рахує стрік/%вивчено/ризик, неактивні зверху;
detail дає прогрес по колодах і слабкі слова, що відповідають реальним помилкам.
Bulk-запити (4-5 на overview незалежно від кількості учнів) → <1с на 100 учнів.

**Тести:** `scratchpad/test_m6.py` + M6-асерти в repo `tests/test_teacher_decks.py`.
Разом **127 тестів PASSED**. Build OK.

---

## M7 — Онбординг-пакет тенанта ✅

**Документи:**
- `docs/operator_new_tenant_ua.md` — чекліст ОПЕРАТОРА: BotFather (назва/username/
  аватар/кнопка-меню), `scripts/add_tenant.py`, Redeploy, призначення role=teacher,
  смоук-тест. ≤30 хв на цикл.
- `docs/teacher_welcome_ua.md` — нетехнічна памʼятка ВИКЛАДАЧУ: що надіслати
  оператору (назва+лого+перший список), як завантажувати колоди, читати дашборд,
  ділитися посиланням. ≤5 хв дій викладача.

**Код:** `branded_welcome(lang, brand)` у `bot_i18n.py` (uk/en/es/pl/de/fr) — вітання
учню white-label тенанта від імені бренду викладача, БЕЗ згадок WordSnap. `cmd_start`
для тенанта ≠ 1 шле саме його (тенант 1 — звичне WordSnap-вітання).

**Тест:** `tests/test_branded_welcome.py` — бренд підставлено, «WordSnap» відсутнє.
