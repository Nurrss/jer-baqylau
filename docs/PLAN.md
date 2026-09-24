# ЖерБақылау — план работ

> Источник требований: `PROMPT_Claude_Code_ZemKontrol.md`. Этот файл описывает, **как** мы его реализуем.
> Статус: черновик, ждёт подтверждения перед Фазой 0.

## 0. Принятые вводные (из ответов на вопросы)

| Вопрос | Решение |
|---|---|
| Состав команды | Пока один человек ведёт и web, и api. Разделение зон A/B в `CLAUDE.md` сохраняем, чтобы второй человек мог подключиться без переделок |
| Репозиторий | Приватный GitHub-репозиторий, создаётся через `gh` в Фазе 0 |
| БД для разработки | Отдельный **dev-проект Supabase** (настоящие PostGIS, Storage, Realtime, Auth). Прод — второй проект Supabase. `docker-compose.yml` всё равно есть: `redis` + `api`, а `postgis` запускается профилем `offline` как запасной вариант |
| Telegram / аккаунты | Токен бота и аккаунты есть. Всё, что требует логина, я запрашиваю явно: когда, что и какой командой (см. §3) |
| GeoJSON организаторов | Пока нет. Генерируем свои участки вокруг Тараза; адаптер `packages/seed/organizers/` делаем сразу, с гибким маппингом полей |

## 1. Ключевые технические решения (пойдут в `docs/DECISIONS.md` как ADR)

1. **Подключение к Supabase Postgres:** через **Supavisor session pooler** (порт 5432, `aws-0-<region>.pooler.supabase.com`). Прямой хост `db.<ref>.supabase.co` доступен только по IPv6, а Railway и многие домашние сети с этим плохо справляются. Transaction pooler (6543) не берём: asyncpg ломается на prepared statements.
2. **Два URL БД:** `DATABASE_URL` (asyncpg, для приложения) и `DATABASE_URL_SYNC`/тот же URL для Alembic. Код не знает, Supabase это или локальный PostGIS.
3. **Realtime:** бэкенд пишет в `events`, `signals`, `parcels`. Фронт подписан через Supabase Realtime `postgres_changes` (RLS: SELECT для `authenticated`). Fallback: `GET /api/v1/events?since=<id>` раз в 5 с, включается, если нет `VITE_SUPABASE_URL` или сокет недоступен.
4. **Аутентификация инспектора:** Supabase Auth (email+пароль). Бэкенд проверяет JWT через JWKS проекта (`/auth/v1/.well-known/jwks.json`), а если проект на legacy-HS256, то через `SUPABASE_JWT_SECRET`. Служебные эндпоинты (`/dev/*`) закрыты заголовком `X-Service-Key`.
5. **Бот в процессе API:** aiogram 3. `BOT_MODE=polling` локально, `webhook` на Railway. Webhook отвечает 200 сразу, обработка идёт в `asyncio` task с идемпотентностью по `update_id` (Redis `SETNX` с TTL). Скачивание фото, превью и загрузка в Storage уходят в фон.
6. **Локализация бота:** Fluent (`aiogram-i18n` + `fluent.runtime`), файлы `apps/api/app/bot/locales/{ru,kk}/*.ftl`. Веб: i18next, `apps/web/src/locales/{ru,kk}.json`. Нормативный контент лежит в `packages/seed/knowledge/{ru,kk}/*.yaml`.
7. **Машина состояний:** один модуль `app/domain/state_machine.py` описывает переходы для Parcel, Signal и Application. Недопустимый переход → 409 `INVALID_TRANSITION`.
8. **Геопривязка сигнала:** сначала `ST_Contains(parcel.geometry, point)`, иначе ближайший участок через `ST_DWithin(geography, 100)` + `ORDER BY ST_Distance`. Дедупликация: `ST_DWithin(geography, 30)` за 7 дней → `duplicate_of = корневой сигнал`.
9. **Генерация участков:** детерминированный генератор (seed=42) строит кварталы (сетку улиц со сдвигом и поворотом) вокруг ~42.90N 71.37E; ИЖС-кварталы ближе к городу, с/х-поля на окраинах. Результат сохраняется в `packages/seed/parcels.geojson` и коммитится. В тесте проверяются `ST_IsValid` и отсутствие пересечений.
10. **PDF-акт:** reportlab + шрифт DejaVu Sans (TTF кладём в репо, лицензия свободная).
11. **Спутник:** `MockSentinelProvider` выдаёт детерминированный NDVI по хешу участка + сезонность; `violation_type=UNUSED` и часть `OK` получают низкий NDVI. APScheduler раз в N минут пишет `ndvi_scans` и помечает кандидатов.

## 2. Контракт API (фиксируется в Фазе 1)

База `/api/v1`, все ответы — Pydantic v2. Ошибки в формате `{ "error": { "code", "message", "details" } }`.

| Метод | Путь | Доступ | Назначение |
|---|---|---|---|
| GET | `/health` (без префикса) | public | БД, Redis, бот |
| GET | `/parcels` | inspector | GeoJSON FeatureCollection; `bbox`, `status[]`, `violation_type[]`, `purpose[]`, `overdue` |
| GET | `/parcels/search?q=` | inspector | по кадастровому номеру или адресу, до 10 результатов с центроидом |
| GET | `/parcels/{id}` | inspector | детали + фото (signed URLs) + связанные сигналы + история |
| PATCH | `/parcels/{id}` | inspector | `deadline_at`, `inspector_id` |
| POST | `/parcels/{id}/transitions` | inspector | `{to, comment, violation_type?, deadline_at?}` → 200 / 409 |
| POST | `/parcels/{id}/photos` | inspector | multipart, несколько файлов |
| GET | `/parcels/{id}/act.pdf?lang=ru\|kk` | inspector | акт осмотра |
| GET | `/signals` | inspector | очередь; `status[]`, пагинация |
| GET | `/signals/{id}` | inspector | детали + фото + дубликаты |
| POST | `/signals/{id}/transitions` | inspector | `{to, comment}`; `CONFIRMED` может сразу перевести участок в `VIOLATION` |
| GET | `/applications` | inspector | таблица |
| POST | `/applications/{id}/transitions` | inspector | `{to, comment_ru, comment_kk, inspection_date?}` |
| GET | `/stats/dashboard` | inspector | KPI, сигналы по дням, типы нарушений, ближайшие дедлайны |
| GET | `/satellite/ndvi` | inspector | NDVI по участкам (последний скан) |
| GET | `/export/parcels.geojson`, `/export/parcels.csv` | inspector | экспорт |
| GET | `/events?since=` | inspector | fallback для realtime |
| POST | `/dev/simulate-signal` | service key | эмуляция сигнала из бота (для e2e и плана Б) |
| POST | `/dev/demo-reset` | service key | сброс к сид-данным |
| POST | `/tg/webhook` | Telegram secret | вебхук бота |

Типы фронта: `openapi-typescript` → `apps/web/src/api/schema.d.ts` (коммитится). Команда `make gen-types` берёт `openapi.json`, который бэкенд выгружает в `apps/api/openapi.json` (тоже коммитится) без запуска сервера.

## 3. Что понадобится от тебя (и когда)

| Когда | Что | Как |
|---|---|---|
| Фаза 0 | Разрешение на `brew install uv railway` | я выполню сам |
| Фаза 0 | `gh auth status` должен быть залогинен | `! gh auth login` |
| Фаза 1 | **Dev-проект Supabase** (регион Frankfurt): `Project URL`, `anon key`, `service_role key`, пароль БД, строка **Session pooler** | Dashboard → Project Settings → API / Database → Connect |
| Фаза 1 | Пользователь-инспектор в dev-проекте | Я дам команду или сделаю через Admin API с service key |
| Фаза 3 | `TELEGRAM_BOT_TOKEN` (лучше отдельный dev-бот, чтобы polling и прод-вебхук не конфликтовали) | @BotFather |
| Фаза 3 | Upstash Redis `rediss://…` (для dev можно локальный Redis из docker) | console.upstash.com |
| Фаза 5 | Прод-проект Supabase (те же ключи), `railway login`, `vercel login`, прод-токен бота | команды дам по шагам в `docs/DEPLOY.md` |

Секреты передавай **только в `.env`**: я создам `.env` из `.env.example`, ты вписываешь значения сам. В чат ключи не присылай.

## 4. Фазы

### Фаза 0 — Каркас
- Монорепо: `apps/api`, `apps/web`, `packages/seed`, `supabase/`, `scripts/`, `docs/`.
- `apps/api`: uv, FastAPI-скелет, `/health`, настройки (pydantic-settings), structlog-логи, Dockerfile (multi-stage, uv).
- `apps/web`: Vite + React 18 + TS + Tailwind + shadcn/ui + i18next-скелет, `vercel.json`.
- `docker-compose.yml`: `redis`, `api`, `postgis` (profile `offline`).
- `Makefile` + `scripts/*.py` (кроссплатформенные дубли): `up`, `down`, `migrate`, `seed`, `demo-reset`, `test`, `lint`, `gen-types`, `dev-api`, `dev-web`.
- Линтеры: ruff, mypy (strict на `app/domain`, `app/services`), eslint, prettier. pre-commit по желанию.
- CI: GitHub Actions, два job'а (api: ruff+mypy+pytest с сервисом `postgis/postgis`; web: lint+tsc+build).
- `.gitattributes`, `.gitignore`, `.env.example`, `README.md`, `docs/DECISIONS.md`.
- **DoD:** `make up` → `/health` ok; `npm run build` в web без ошибок; CI зелёный; коммит, push в приватный репо.

### Фаза 1 — Данные и контракт API
- SQLAlchemy-модели и Alembic-миграции (включая `CREATE EXTENSION postgis`, GiST-индексы, enum'ы).
- `supabase/*.sql`: RLS, publication `supabase_realtime` для `events`/`signals`/`parcels`, бакет `photos` (private).
- Машина состояний, сервисный слой (`ParcelService`, `SignalService`, `ApplicationService`, `EventBus`, `AuditLog`).
- Генератор сид-данных, идемпотентный сид, `demo_reset`.
- Все REST-эндпоинты из §2 (кроме PDF и NDVI, которые могут вернуть 501 до Фазы 6, но в UI не показываются), JWT Supabase.
- pytest: переходы, геопривязка, дедупликация, валидность полигонов, авторизация. Тесты гоняются на PostGIS из docker (testcontainers-подобно через compose), **не** на dev Supabase.
- **DoD:** pytest зелёный, `openapi.json` и `schema.d.ts` сгенерированы и закоммичены.

### Фаза 2 — Карта инспектора (web)
Логин, layout, карта (полигоны по статусам, hover, тултип, легенда со счётчиками, фильтры, поиск + flyTo, подложки OSM/Esri), карточка участка (характеристики, степпер, модалки переходов, дедлайн, галерея + drag&drop, история), страницы Сигналы и Заявления, RU/KZ, светлая и тёмная темы, skeleton и пустые состояния.
**DoD:** `tsc` + `build` без ошибок, скриншоты ключевых экранов через Playwright, RU/KZ переключаются.

### Фаза 3 — Бот
/start + язык, главное меню, статус заявления (нормализация номера), база знаний с листанием, «Народный контроль» (FSM: категория → гео + bbox → 1–5 фото/альбом/файл → описание → подтверждение с Nominatim → SIG-код), «Мои обращения», подписки, rate limit, таймаут FSM, «Отмена» на любом шаге.
**DoD:** все сценарии работают в polling с реальным dev-токеном; логика (нормализация, FSM-переходы, rate limit, локали без пропущенных ключей) покрыта тестами.

### Фаза 4 — Realtime и уведомления
Supabase Realtime на фронте (toast, анимация, звук с отключением, перекраска участка), fallback-поллинг, `NotificationProvider` (Telegram) и Notifier на все переходы Signal/Parcel/Application с подписчиками, на языке жителя.
**DoD:** `python scripts/e2e_smoke.py --base-url http://localhost:8000` проходит.

### Фаза 5 — Деплой
Прод Supabase + Upstash + Railway + Vercel строго по `docs/DEPLOY.md`, `scripts/set_webhook.py`, CORS.
**DoD:** `e2e_smoke.py --base-url <prod>` проходит; ручной прогон цикла с телефона.

### Фаза 6 — Вау и масштаб
Дашборд (KPI + графики), NDVI-слой + APScheduler-скан, PDF-акт, UI дедупликации («N жителей сообщили»), адаптеры `CadastreProvider`/`SatelliteProvider`/`NotificationProvider`/`StorageProvider`, экспорт GeoJSON/CSV, `docs/ARCHITECTURE.md` с Mermaid.

### Фаза 7 — Полировка и демо
UX-мелочи, README со скриншотами и прод-ссылками, `docs/DEMO_SCRIPT.md`, проверка «с нуля»: `git clone → .env → make up`.

## 5. Порядок работы соло

Раз ты один, фазы 2 и 3 можно вести параллельно **субагентами** после фиксации контракта: один работает в `apps/web`, другой в `apps/api/app/bot`, каждый в своём git worktree. Я их координирую, ревьюю и мержу. Коммиты по conventional commits, на каждой фазе тесты и линтеры обязательны.

## 6. Риски и страховка

| Риск | Страховка |
|---|---|
| Сеть на площадке | `docker compose --profile offline` + локальный фронт; `simulate-signal` с ноутбука |
| Supabase Realtime не пришёл | поллинг `/events` включается автоматически |
| Telegram повторно доставляет апдейты | мгновенный 200 + дедуп `update_id` в Redis |
| Nominatim лимиты | кэш в Redis/БД, User-Agent, fallback на координаты |
| Неточная нормативка/казахский | пометки «требует сверки» / «требует вычитки» в `DECISIONS.md` и в YAML |
