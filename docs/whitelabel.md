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

---

## M8 — Sentry + захисні дрібниці ✅

**Sentry (SDK вже був — додано мультитенантність і скрабінг):**
- Бекенд: middleware ставить тег `tenant_id` на кожен запит (сегментація помилок
  по бренду). `_filter_event` скрабить `X-Telegram-Init-Data`/`Authorization`/
  `Cookie` заголовки і query з `hash=` — жодного PII/токенів у Sentry.
- Фронтенд: `setSentryTenant(tenant_id, slug)` викликається при завантаженні
  config у `TenantContext`.

**Rate limit:** `core/rate_limit.py` (in-memory sliding window) — `POST/PATCH
/api/teacher/decks` обмежені 30 записів/60с на викладача (429 при спамі парсера).

**Тести:** `tests/test_rate_limit.py`. Разом 126 pure-logic PASSED; build OK.

**Фаза 1 (M1–M8) завершена.** Далі — Фаза 2: M9 (календар уроків), M10 (передурочний дайджест).

---

# Фаза 2

## M9 — Календар уроків ✅

**Схема:** `teacher_availability (tenant_id, teacher_user_id, weekday, start_min,
end_min)` — тижневий шаблон у ЛОКАЛЬНІЙ таймзоні викладача; `teacher_closed_dates`;
`lessons (tenant_id, teacher_user_id, student_user_id, starts_at_utc, duration_min,
status, reminder_24/1_sent, digest_sent)`. Анти-подвійне-бронювання: **частковий
UNIQUE індекс** `(tenant_id, teacher_user_id, starts_at_utc) WHERE status='booked'`.
`tenants.lesson_duration_min` (60) + `cancel_cutoff_hours` (12).

**Часові пояси:** зберігаємо в UTC, доступність — у tz викладача (`users.timezone`),
показ — у tz кожного користувача. Слоти генеруються з шаблону, конвертуються в UTC
через ZoneInfo (коректний DST), фільтруються від минулих/закритих/заброньованих.

**`core/calendar_service.py`:** availability CRUD, `free_slots` (генерація+TZ),
`book_lesson` (валідація легальності слота + insert з catch IntegrityError →
'slot_taken'), `cancel_lesson` (дедлайн для учня, викладач без обмеження),
`list_lessons`.

**API (`webhook/calendar_routes.py`):** викладач — availability GET/PUT, closed_date,
lessons, cancel; учень — slots, my, book, cancel. Підтвердження бронювання/скасування
йде ОБОМ у їх локальному часі з бота тенанта.

**Шедулер (`scheduler/lesson_reminder.py`):** щохвилини; за 24 год і за 1 год до
уроку шле обом з бота тенанта (прапори reminder_24/1_sent проти повторів).

**Фронтенд:** `LessonsPage.jsx` (учень: вільні слоти по днях, бронювання в тап, мої
уроки + скасування). `TeacherPage` → вкладка «Календар» (`CalendarManager`: тижневий
редактор доступності по днях, заброньовані уроки + скасування). NavBar: «Уроки» для
white-label учнів; вкладка «Викладач» містить календар.

**Критерій (перевірено):** слоти генеруються з урахуванням TZ (Warsaw 10:00 → учень
NY бачить 04:00); бронювання в один тап; подвійне бронювання блокується (unique +
транзакція); скасування учнем не пізніше 12 год; закрита дата прибирає слоти.

**Тести:** `tests/test_calendar.py` (repo) + `scratchpad/test_m9.py`. Разом **130
тестів PASSED** (виправлено крос-loop у DB-тестах через `tests/conftest.bind_test_engine`).

## M10 — Передурочний дайджест ✅

**Шедулер (`scheduler/lesson_digest.py`):** щохвилини; за `tenants.digest_lead_hours`
(дефолт 3) до уроку, для booked-уроків без `digest_sent`, шле з бота тенанта:
- **Викладачу:** імʼя учня, час (у tz викладача), стрік + повторень за 7д, прогрес
  по колодах, топ-5 слабких слів.
- **Учню:** нагадування (у tz учня) + inline web_app кнопка «Повторити слабкі слова»
  → відкриває Mini App на `?src=weak`.

**Дані = ті самі агрегати M6** (`teacher_stats.student_detail`) — не дублюємо логіку.
Спільний `teacher_stats.weak_word_ids(user_id)` (дашборд + дайджест + ендпоінт учня).

**Ендпоінт учня:** `GET /api/review/weak` — слабкі слова того, хто викликає,
серіалізовані як review-слова.

**Фронтенд:** `ReviewPage` при `?src=weak` вантажить `getWeakReviewWords`; `App`
має `DeepLinkHandler` — ловить `?src=weak` на старті і веде в `/review?src=weak`.

**Критерій (перевірено):** дайджест вибирає уроки у вікні lead (2h→так, 10h→ні),
викладач бачить агрегати+слабкі слова, учень — нагадування+кнопку; `digest_sent`
проти повторів (ідемпотентно). Тест: `scratchpad/test_m10.py`. **130 тестів PASSED.**

**Фаза 2 (M9–M10) завершена.** Далі — Фаза 3 (M11–M18) хвилями.

---

# Фаза 3 (M11–M18) — розширення цінності

## M11 — Снап викладача: фото → колода ✅
`openai_client.extract_word_pairs_from_image` (vision, окремий промпт під словниковий
список, detail=high, до 40 пар). `POST /api/teacher/decks/from_photo` — превʼю пар
(не зберігає), поважає `ai_snap_available` (429 `ai_snap_limit_reached`), рахує
`incr_ai_snap_usage`. Фронт: кнопка «📷 Створити з фото» у формі колоди → base64 →
пари вставляються у textarea як «слово - переклад» → викладач редагує → звичайне
збереження. Ліміт вичерпано → мʼяке повідомлення «доступно з наступного місяця».
_Тести — у фінальному проході._

## M12 — Алерти ризику відтоку ✅
`scheduler/churn_alert.py` (кожні 6 год): для кожного тенанта знаходить учнів
без активності ≥ `tenants.churn_alert_days` (5) і шле викладачу одне попередження
з бота тенанта. Анти-спам: `users.last_churn_alert_at` (не частіше 1×/7 днів на учня).
Бейдж «в ризику» вже є в дашборді M6 (`at_risk`). _Тести — у фінальному проході._

## M13 — Домашнє завдання з дедлайном ✅
`homework` table + `core/homework_service.py` — статус обчислюється динамічно
(done = усі слова колоди пройдені ≥1; overdue = дедлайн минув; in_progress; assigned).
`POST /api/teacher/decks/{id}/homework` (призначення), `GET /api/homework` (учень).
Нагадування за 24 год до дедлайну — у `lesson_reminder._process_homework`. Інтеграція
з передурочним дайджестом M10: статус ДЗ у повідомленні викладачу. Фронт: дедлайн-input
у EditDeck; секція «Домашнє завдання» з бейджами статусу у LessonsPage.
_Тести — у фінальному проході._ **Хвиля A (M11–M13) завершена.**

---

# Фаза 3, хвиля B

## M14 — Режим школи: кілька викладачів і групи ✅
**Схема:** `groups (tenant_id, name, teacher_user_id)`, `group_members`, `decks.group_id`,
`tenants.is_school`, `users.is_active_teacher`. Ролі: owner/teacher/student (вже були).
`core/group_service.py`: викладачі (owner додає за telegram_id, деактивує), групи
(CRUD, склад), `student_ids_for_teacher` (ізоляція).

**Ізоляція в школі:** викладач бачить лише своїх учнів (члени його груп) і свої
колоди; owner — усе. Реалізовано через `_school_scope` в `teacher_routes` →
`students_overview(restrict_ids=…)` + `list_teacher_decks(owner_user_id=…)`. Solo-тенанти
не зачеплені (scope = None). Колода адресується: всім / групі / обраним (`create_deck`
group_id → матеріалізація членам групи).

**Ендпоінти:** `/api/teacher/school`, `/teachers` (owner CRUD), `/groups` (+members).
**Фронт:** вкладка «Школа» (owner: викладачі; усі: групи+склад), опція «Групі» у формі колоди.

**Відкрито (фінальний прохід):** календар per-teacher у школі — зараз
`get_tenant_teacher_id` бере першого викладача; для повної школи бронювання учня
має вести до викладача його групи. Тести ізоляції школи — у фінальному проході.

---

# Фаза 3, хвиля В

## M16 — Лідерборд групи ✅
`core/leaderboard_service.py` — тижневий рейтинг (ISO-тиждень Пн→тепер) за
повтореннями + стріком, у межах групи (school) або всіх учнів тенанта. Минулі
тижні «зберігаються» без окремої таблиці — рахуються з історії reviews за будь-яке
вікно. Анти-накрутка: distinct (user_id, word_id, day) — спам-тапи по одному слову
не крутять. `GET /api/leaderboard/weekly` (учень: своє місце), `GET /api/teacher/leaderboard`
(викладач: топ-3 + готове повідомлення-привітання). Фронт: топ-3 у дашборді викладача,
«Рейтинг тижня» з місцем учня у LessonsPage. _Тести — у фінальному проході._

## M17 — Озвучка слів (TTS) ✅ (наявна інфраструктура)
Кнопка вимови **вже реалізована** через браузерний `speechSynthesis` (`utils/speak.js`
+ `components/SpeakButton`), вбудована в картки, квіз, список слів, деталі слова;
покриває pl/de/en (+es/uk/fr). Критерій M17 («кнопка вимови на картці/у квізі»)
задоволено. Серверний TTS (OpenAI/Google/Azure) з кешем аудіо — опційний upgrade
якості, не потрібен для критерію; відкладено.

## M15 — Місячний PDF-звіт про прогрес ✅
`core/pdf_report.py` (reportlab) — PDF по учню: бренд тенанта (кольори/назва, без
згадок WordSnap), імʼя, повторення/вивчено/нові слова/стрік, графік активності за
місяць. `scheduler/monthly_report.py` — 1-го числа генерує по кожному учню тенантів
з `tenants.monthly_report_enabled` і шле викладачу файлом (send_document з бота
тенанта). Анти-дубль: `app_state` ключ per-tenant з міткою місяця. Опція вмикається
оператором (SQL/UI). Перевірено: валідний PDF, бренд є, «WordSnap» відсутнє.

## M18 — Демо-тенант «Мовна школа» (шкільний режим) — оператор
Створюється оператором після мержу M14: `add_tenant.py` + `UPDATE tenants SET
is_school=true`, 2 викладачі (role=teacher), 2 групи, кілька учнів, колоди на групу,
активний лідерборд. Потребує реальний бот BotFather — автоматизувати не можна (як M3.5).
Кроки — у `docs/operator_new_tenant_ua.md` (+ school-специфіка).

---

## Фінальний тестовий прохід ✅
Додано repo-тести (gated на TEST_DATABASE_URL) для відкладених milestone-ів:
- `test_school.py` (M14) — ізоляція між викладачами, групи, груповий таргет колоди,
  owner-бачить-усе, деактивація викладача.
- `test_homework.py` (M13) — статуси assigned/in_progress/done/overdue.
- `test_leaderboard.py` (M16) — ранжування, анти-накрутка (distinct word-day), self-rank.
- `test_churn.py` (M12) — вибір неактивних + анти-спам cooldown.
Разом **134 тести PASSED**. Міграції: 101 ідемпотентних, 0 fail. Фронт `npm run build` OK.
M11 (vision) і M15 (PDF) перевірено окремо (генерація PDF валідна; vision потребує OpenAI).

## Підсумок
**Реалізовано M1–M17** (M18 — оператор-run). 17 PR у стеку (#1–#16 на GitHub;
деякі milestone-и об'єднані). WordSnap лишається тенантом 1 без змін. Зливати PR
по черзі; `pg_dump` перед першим мержем у main (Railway автодеплой).

---

## M19 — Брендоване меню ботів + дотюнінг інтерфейсу ✅
Після питання оператора: боти окремі на тенант, але код спільний — тож зробили
per-tenant брендинг на рівні Telegram + прибрали WordSnap-артефакти в додатку.

**Бот (`core/bot_menu.py`, `setup_tenant_bot` на старті для кожного бота тенанта):**
- Брендоване меню команд БЕЗ білінг-команд (start/review/app/stats); окреме
  chat-scope меню викладачу (owner_telegram_id) — /app → «Кабінет викладача».
- Кнопка-меню (`set_chat_menu_button` → WebApp) ставиться автоматично — оператору
  більше НЕ треба робити це вручну в BotFather.
- Опис/short-опис бота від бренду тенанта (без згадок WordSnap).
Головний бот WordSnap (тенант 1) — без змін (`setup_bot_commands`).

**Інтерфейс Mini App (тюнінг під тип/роль):**
- Вкладка «Школа» у TeacherPage показується ЛИШЕ коли `is_school` (solo — без неї).
- White-label учні більше не бачать WordSnap-артефактів лімітів: лічильник
  «X/ліміт» у SnapCard і модалка «денний ліміт досягнуто» — тільки для тенанта 1
  (у white-label лімітів/оплати немає). Реалізовано через `useTenant().isDefaultTenant`.
- (Раніше вже: брендовані кольори/лого/назва, приховані ціни/Pro, «Уроки» замість
  «Пісні» для white-label учнів, вкладка «Викладач» для teacher/owner.)

134 тести без регресій; build OK.

---

## Продакшн-деплой + перший тенант (2026-07-12)

Перший реальний викат усієї white-label платформи в прод і підключення першого
викладача — **«Польська з Мартою»** (@martapolish_bot).

**Мердж і деплой:**
- Весь стек (m1…m19) fast-forward-змерджено в `main` (main `e00ecc1` = тіп m19).
- Перший Docker-білд на Railway впав: `backend/requirements.txt` містив злиплий
  рядок `pytest-asyncio==0.24.0reportlab==4.2.5` (M15 дописав reportlab без `\n`).
  Виправлено окремим комітом `e8d5ebc` (розбито на два рядки).
- Перед міграцією знято `pg_dump` продової Supabase (потрібен pg_dump ≥ 17 —
  сервер PG17; `brew install libpq` дає v18). **Нюанс:** `DATABASE_URL` іде через
  transaction-пулер `:6543`, яким pg_dump/psql не працюють — для дампу/psql
  міняти порт на session `:5432` того ж хоста.
- Автодеплой (Railway, сервіс `worker`, проєкт eloquent-serenity) застосував
  `auto_migrate`: **101 ok, 0 failed** на проді. Обидва боти полінгують на
  спільному диспетчері: `@WordSnapBot` (t1) + `@martapolish_bot` (t2).

**Тенант `marta` (id=2):** заведено через `scripts.add_tenant`
(slug=marta, «Польська з Мартою», bot_id 8845995169, plan=trial,
кольори `#DC2626/#F59E0B`, billing_ui=false). Бот сконфігуровано (команди,
кнопка-меню→Mini App, брендовані опис/short) — і вручну через Bot API, і
`setup_tenant_bot` на старті. Викладач (owner) = Volodymyr (tg 469478065,
`role=teacher`); `logo_url` поки null.

**E2E-верифікація ізоляції** (наскрізно через прод
`https://worker-production-abd5.up.railway.app/api/tenant/config`, з підписаною
initData у заголовку `X-Telegram-Init-Data`):
- підпис токеном Марти → `tenant_id=2`, бренд Марти, `billing_ui_enabled=false`;
- підпис токеном WordSnap → `tenant_id=1`, «WordSnap», `billing_ui_enabled=true`.
Резолвинг тенанта з підпису бота (`tg_auth.resolve_init_data`) працює; WordSnap
(тенант 1) не зачеплено.

**Побічний фікс (не white-label):** `core/user_service.disable_reminders_if_blocked`
використовував голий `update(User)`, а `core/user_service.py` не імпортував
`update` із SQLAlchemy → `NameError: name 'update' is not defined` щоразу, коли
юзер заблокував бота (функція мала вимкнути йому нагадування, але падала, тож
заблоковані ретраїлися вічно). Додано `update` в імпорт.

**Лишилось:** лого Марти; за потреби — перепризначити викладача на акаунт самої
Марти (натисне Start → `owner_telegram_id` + `role=teacher` на її tg-id).

---

## Teacher UX — доробки за фідбеком Марти (2026-07-12, коміт 5292d73)

Після першого тесту кабінету викладача — набір UX-змін (усе гейтоване під
white-label / не чіпає WordSnap-тенант 1). Бекенд → Railway, фронт → Vercel
(обидва git-connected до main). Міграція: `✓ tenants.bot_username` (102 ok).

**Статистика учня (тільки не-дефолтний тенант):** прибрано згадки оплати/Pro,
плитки «Витрачено всього» та «Днів серії», картки XP-циклу + lifetime-hero і
драбину «Нагороди за XP» (усе привʼязане до Pro-знижок). Замість них — кільце
прогресу вивчення (`components/WordsProgress.jsx`): свідомо single-hue (брендовий
тон на нейтральному треку), НЕ двоколірний донат — бо в білому лейблі `--violet`
може бути червоним, і red/green поряд плутав би дальтоніків. Гейт — `!isDefaultTenant`.

**Кабінет викладача:**
- *Учні:* кнопка «🔗 Поділитися ботом» (у порожньому стані й у шапці списку).
  Для цього додано per-tenant `tenants.bot_username` (заповнюється на старті через
  `getMe` → `set_tenant_bot_username`), проброшено в `/api/tenant/config` →
  `TenantContext`. Лінк — `https://t.me/<bot_username>`, шар через
  `Telegram.WebApp.openTelegramLink(t.me/share/url…)`.
- *Рейтинг:* тижневий «Топ тижня» (за повтореннями) замінено на «🏆 Рейтинг за XP»
  — усі учні тенанта, сорт за `total_xp` (додано в `teacher_stats.students_overview`);
  XP також показано в кожному рядку учня.
- *Календар:* нативні time-інпути → дропдауни (`TimeSelect`, 30-хв крок). Розбито на
  три блоки: «Вільні години» (шаблон, з якого учні самі бронюють), «Забронювати урок
  вручну» (викладач ставить урок будь-кому на будь-який час — `POST /api/teacher/lessons`
  → `calendar_service.create_manual_lesson`, зберігає захист від подвійного бронювання),
  і денний «Розклад» (уроки згруповані за локальною датою: хто і о котрій).

**E2E (підписана initData, прод):** config → `bot_username=martapolish_bot`,
billing off; `/api/teacher/students` та `/api/teacher/availability` → 200.
`miniapp/dist` build OK; прод-домен віддає свіжий бандл.

**Ще відкрито:** лого Марти (`logo_url` null); `total_xp` у рядках учнів реально
видно буде, коли зʼявляться учні (зараз у тенанті лише викладач).

---

## Окрема оболонка викладача (role-aware shell, 2026-07-13, коміт 1f42924)

За фідбеком: у додатку багато чого суто для учня, а викладач досі бачив
учнівський UI + одну вкладку. Зробили **розділення за роллю в межах однієї
кодової бази** (не окремий додаток — бо white-label = один код/деплой/диспетчер,
один URL Mini App на бота). Фронт-онлі; Vercel git-connected до main.

- **`contexts/RoleContext.jsx`** — роль із `/api/stats.role` (миттєво з кешу,
  потім освіження). `teacherMode = (teacher|owner) && !studentPreview`.
- **Оболонка викладача:** нижня навігація — **Учні / Колоди / Календар /
  Статистика** (усі ведуть на `/teacher?tab=…`); `/` для викладача редіректить
  у кабінет. `TeacherPage` бере активний таб із `?tab=` (єдине джерело істини для
  нижньої навігації й внутрішніх пігулок).
- **Нова вкладка «Статистика»** (`TeacherStats`): зведені KPI (учнів /
  активних 7д / у ризику / сер. % вивчено) + детальний прогрес **по обраних
  учнях** (перевикористовує `StudentPicker` + `StudentDetail`).
- **«👁 Як учень»** — тумблер прев'ю: тимчасово рендерить учнівський додаток із
  банером повернення (`studentPreview` у sessionStorage). Учнівський досвід — без
  змін; для не-викладачів нічого не змінюється.

Верифіковано на проді: `/api/stats.role=teacher` для власника → оболонка
активується; miniapp build+deploy OK; Railway (бекенд без змін) — чистий рестарт.

---

## Колоди: необовʼязковий переклад + сповіщення учням (2026-07-13)

- **Переклад необовʼязковий.** `parse_deck_entries` тримає рядки без роздільника
  (саме слово) → `autofill_translations` заповнює переклад через `get_word_data`
  (та сама AI+кеш, що й у WordSnap; target = мова вивчення, native = мова учнів).
  Якщо AI не дав — лишаємо слово (пара не буває порожня). Викладач може вводити
  просто список польських слів.
- **Сповіщення учням.** `notify_students_new_words` (best-effort) шле кожному
  учневі-адресату повідомлення з бота тенанта при створенні колоди («нова
  колода «X» (N слів)») і при дописуванні слів («N нових слів»).

## Камера прямо в застосунку (2026-07-13)

- **`components/CameraCapture.jsx`** — жива камера через `getUserMedia` (прев'ю +
  «Зняти» кадр у base64). Працює на десктопі (вебкамера) і в мобільних webview;
  фолбек на нативну камеру пристрою через `<input capture="environment">`, коли
  живий доступ недоступний. Потік завжди зупиняється при закритті.
- **Кабінет викладача:** у формі колоди — «📷 Зробити фото» (жива камера) поряд
  із «🖼 З файлу»; той самий пайплайн розпізнавання (`createDeckFromPhoto`).
- **WordSnap main (тенант 1 теж):** `SnapCard` дістав «📷 Фото» + «🖼 З файлу».
  Новий `POST /api/snap/photo` (vision-екстракт кандидатів `extract_words_from_image`,
  поважає місячний AI-ліміт тенанта) → кандидати показуються чіпами → «Додати N»
  через `/api/words/bulk`. i18n: `snap.photo/file/extracting/photo_empty/…` (en+uk).

## Фікс BackButton + кнопка «закрити» (2026-07-13)

- Telegram скидає `BackButton.onClick` при нативних оверлеях (invoice/popup/share
  через `openTelegramLink`) — після «Поділитися ботом» кнопка «назад» була мертва.
  Перевстановлюємо обробник при поверненні фокуса/видимості (offClick→onClick).
- `/teacher` — кореневий екран (без «назад» → Telegram показує нативну ✕).
- Явна кнопка «закрити» (`tg.close()`) у `AppBar` для white-label (WordSnap без змін).

## Фікси review-флоу за фідбеком Марти (2026-07-13/14, коміт c30d3de)

1. **Викладачу приходили учнівські нагадування** → шедулери `reminder`/`reengage`/
   `streak_save` тепер фільтрують `role='student'`.
2. **Напрям колоди** (картка показувала укр. слово замість польського) → слово має
   бути мовою вивчення; форма колоди підказує це; додано **видалення колоди**
   (`DELETE /api/teacher/decks/{id}` + `deck_service.delete_deck` (прибирає й
   матеріалізовані слова) + кнопка 🗑 у `EditDeck`), щоб перестворити хибну колоду.
3. **Нема опису як в WordSnap** → `_materialize` тепер збагачує НОВІ слова колод
   через кешований `get_word_data`+Unsplash (examples/memory_tip/part_of_speech/
   difficulty/image) — лише для відсутніх у юзера слів (без повторних Unsplash на
   sync). Review-картка показує до 3 прикладів із поясненням (було 1).
4. **Аудіо-кнопка** → `SpeakButton` перевіряє підтримку на рендері; `speak.js`
   оновлює голоси, скасовує лише коли реально грає, +локаль `fr`, +Chrome resume.
5. **«Назад» після рейтингу** → `TelegramBackButton.onBack` фолбечить на `/`, коли
   історії немає (дип-лінк `/review` з нагадування).

## Маркетинг цього дня (окремо від коду)

- Розсилка про камеру → 88 WordSnap-юзерам (тенант 1, `scripts/broadcast_camera_snap.py`),
  55 доставлено.
- Соц-пости через окреме репо `wordsnap-threads-bot` (Threads + IG + Reels, з
  approval у Telegram): анонс камери (Threads), word-card «payslip» (IG), reel
  «tęskność» (IG Reels + Threads). Полагоджено health-alert (протермінований
  IG-токен уже оновлено в GitHub Secrets 12.07; підтверджено наскрізним reel).
