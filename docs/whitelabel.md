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
