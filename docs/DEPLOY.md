# Деплой «ЖерБақылау»

Итоговая схема: **Supabase** (PostGIS, Auth, Storage, Realtime) · **Upstash** (Redis для FSM бота) ·
**Railway** (API + бот + планировщик, один контейнер) · **Vercel** (веб-панель).

Время: ~40 минут. Шаги с 🔐 требуют твоего входа в аккаунт — Claude их не выполняет.

> Секреты вписываются только в `.env.production` (локально, в git не попадает) и в переменные Railway/Vercel.
> Никогда не вставляй `service_role`/`secret` ключ и токен бота во фронтенд или в чат.

---

## 0. Подготовка

```bash
cp .env.example .env.production     # сюда будем складывать прод-значения
```
Сгенерируй два случайных секрета и сразу впиши в `.env.production`:
```bash
python3 -c "import secrets; print('SERVICE_API_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('TELEGRAM_WEBHOOK_SECRET=' + secrets.token_urlsafe(32))"
```

## 1. Supabase 🔐

1. https://supabase.com/dashboard → **New project**. Регион **Frankfurt (eu-central-1)** — ближайший к Казахстану.
   Задай и сохрани пароль БД.
2. **Database → Extensions** → включи `postgis`.
3. **Project Settings → API Keys** — скопируй в `.env.production`:
   - `SUPABASE_URL` = Project URL (`https://<ref>.supabase.co`)
   - `SUPABASE_ANON_KEY` и `VITE_SUPABASE_ANON_KEY` = **anon / publishable** ключ
   - `SUPABASE_SERVICE_ROLE_KEY` = **service_role** ключ (вкладка *Legacy API keys*, JWT-формат `eyJ…`)
   - `VITE_SUPABASE_URL` = тот же Project URL
4. Если во вкладке **JWT Keys** проект использует *Legacy JWT secret* (HS256) — скопируй его в `SUPABASE_JWT_SECRET`.
   Если используются новые асимметричные ключи (JWKS) — оставь пусто, API сам проверит подпись.
5. **Connect** (кнопка вверху) → **Session pooler** → скопируй URI в `DATABASE_URL`, подставив пароль
   и добавив `?sslmode=require`:
   ```
   DATABASE_URL=postgresql://postgres.<ref>:<PASSWORD>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   ⚠️ Нужен именно **Session pooler, порт 5432** (прямой хост только IPv6, transaction pooler ломает asyncpg — ADR-002).
6. **Authentication → Sign In / Providers** → *Email* включён, **«Allow new users to sign up» — выключить**
   (инспекторов создаём сами). Дополнительно впиши `INSPECTOR_EMAILS=inspector@jer.kz` — только эти почты пустит API.
7. Остальные прод-значения в `.env.production`:
   ```
   ENV=production
   AUTH_MODE=supabase
   STORAGE_BACKEND=supabase
   LOG_JSON=true
   BOT_MODE=webhook
   DEMO_INSPECTOR_EMAIL=inspector@jer.kz
   DEMO_INSPECTOR_PASSWORD=<придумай надёжный пароль>
   DEMO_INSPECTOR_NAME=Инспектор Демо
   ```
8. Схема, RLS, Realtime, бакет, сид и пользователь-инспектор — одной серией команд с твоего компьютера:
   ```bash
   export JER_ENV_FILE=.env.production
   make migrate          # таблицы + PostGIS-индексы
   make supabase-sql     # RLS, publication supabase_realtime, приватный бакет photos
   make seed             # демо-данные (фото загрузятся в Supabase Storage)
   make inspector        # пользователь-инспектор в Supabase Auth
   unset JER_ENV_FILE
   ```
   Без make (Windows): `uv run --project apps/api python scripts/<apply_supabase_sql|seed|create_inspector>.py`,
   миграции — `cd apps/api && uv run alembic upgrade head` (с `JER_ENV_FILE=.env.production` в окружении).

Проверка: **Table Editor** → `parcels` (60 строк), **Storage** → бакет `photos` (private),
**Database → Publications** → `supabase_realtime` содержит `events`, `signals`, `parcels`.

## 2. Upstash Redis 🔐

https://console.upstash.com → **Create database** → регион **eu-central-1 (Frankfurt)** → скопируй
**Redis URL** в формате `rediss://default:<password>@<host>.upstash.io:6379` в `REDIS_URL`.

## 3. Telegram-бот 🔐

1. @BotFather → `/newbot` → токен в `TELEGRAM_BOT_TOKEN` (для прода лучше отдельный бот, не тот, что для разработки:
   один токен не может одновременно работать в polling и webhook).
2. Там же `/setdescription`, `/setabouttext`, `/setuserpic` — по желанию.

## 4. Railway (API + бот) 🔐

```bash
brew install railway            # Windows: npm i -g @railway/cli
railway login
railway init                    # создать проект «jer»
railway up --detach             # первый деплой из текущей папки (railway.json → apps/api/Dockerfile)
railway domain                  # сгенерировать публичный домен, например jer-api.up.railway.app
```
Либо через сайт: **New Project → Deploy from GitHub repo** → репозиторий `jer-baqylau`; `railway.json` в корне
сам укажет Dockerfile и healthcheck `/health`.

> ⚠️ Новый сборщик Railway (Railpack) игнорирует `railway.json` для выбора Dockerfile — задай переменную сервиса
> `RAILWAY_DOCKERFILE_PATH=apps/api/Dockerfile`. Регион ставь рядом с БД:
> `railway scale --service <service> southeast-asia=1 us-west=0 us-east=0 eu-west=0`
> (для Supabase во Франкфурте — `eu-west=1`). Каждый запрос к далёкой БД стоит ~150–200 мс сети.
> На бесплатном плане Railway один проект: сервис можно добавить в существующий (`railway add --service jer-api`).

**Variables** (Service → Variables → *Raw Editor*) — вставь из `.env.production` всё, **кроме** строк `VITE_*`, плюс:
```
PUBLIC_API_URL=https://<railway-домен>
CORS_ORIGINS=https://<vercel-домен>          # заполним после шага 5
RUN_MIGRATIONS_ON_START=true
SEED_ON_START=true
SCHEDULER_ENABLED=true
```
`PORT` Railway задаёт сам. После сохранения переменных сервис перезапустится; при старте он применит миграции,
посеет данные (если пусто) и **сам поставит вебхук** на `PUBLIC_API_URL/tg/webhook`.

Проверка: `curl https://<railway-домен>/health` → `{"status":"ok", "database":true, "redis":true, "bot":"webhook", ...}`.
Вебхук вручную (если нужно): `JER_ENV_FILE=.env.production uv run --project apps/api python scripts/set_webhook.py --info`.

## 5. Vercel (веб-панель) 🔐

```bash
npm i -g vercel
cd apps/web
vercel login
vercel link                     # новый проект, root directory — apps/web
vercel env add VITE_API_URL production          # https://<railway-домен>
vercel env add VITE_SUPABASE_URL production     # https://<ref>.supabase.co
vercel env add VITE_SUPABASE_ANON_KEY production
vercel --prod
```
Или через сайт: **Add New → Project** → репозиторий → **Root Directory = `apps/web`**, Framework = Vite,
Environment Variables — три `VITE_*` выше. `vercel.json` уже содержит SPA-rewrites и заголовки безопасности.

Вернись в Railway и впиши `CORS_ORIGINS=https://<vercel-домен>` (можно несколько через запятую).

### Панель ходит к API через свой домен

`apps/web/vercel.json` проксирует `/api/*` и `/health` на Railway, а `VITE_API_URL` = домен Vercel.
Некоторые сети (DNS-фильтры, мобильные операторы) не резолвят `*.up.railway.app`; так панель
работает везде, где открывается Vercel. Скрипты тоже удобнее запускать через него:
`--base-url https://<vercel-домен>`.

### Спутник

`SATELLITE_PROVIDER=sentinel` — реальные снимки Sentinel-2 L2A (без ключей), `SATELLITE_SCAN_INTERVAL_MINUTES=360`.
Образ API содержит `libexpat1` для GDAL из колёс rasterio.

## 6. Чек-лист после деплоя

| Проверка | Как |
|---|---|
| API жив | `curl https://<api>/health` → `status: ok` |
| Логин инспектора | открыть `https://<vercel>` → войти `inspector@jer.kz` |
| Realtime | индикатор в шапке панели — зелёный «Онлайн» |
| Бот | написать `/start` прод-боту → выбор языка |
| Сквозной цикл | `JER_ENV_FILE=.env.production uv run --project apps/api python scripts/e2e_smoke.py --base-url https://<api> --chat-id <твой chat id>` — сообщения придут тебе в Telegram |
| Сброс демо | `JER_ENV_FILE=.env.production make demo-reset-remote BASE_URL=https://<api>` |

Свой `chat id` можно узнать у @userinfobot.

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `/health` → `database: false` | не session pooler, забыт `?sslmode=require` или неверный пароль |
| Панель: «Нет связи», CORS в консоли | `CORS_ORIGINS` на Railway не содержит домен Vercel (без `/` в конце) |
| Логин проходит, API отвечает 401 | проект на legacy JWT — нужен `SUPABASE_JWT_SECRET` |
| Логин: «не зарегистрирована как инспектор» | почта не в `INSPECTOR_EMAILS` |
| Бот молчит | `BOT_MODE=webhook`, `TELEGRAM_WEBHOOK_SECRET` задан, `PUBLIC_API_URL` = https-домен Railway; `set_webhook.py --info` покажет последнюю ошибку |
| Индикатор «Обновление» вместо «Онлайн» | Realtime не подключился — работает fallback-поллинг (5 с); проверь publication и RLS (`make supabase-sql`) |
| Фото не открываются | `STORAGE_BACKEND=supabase` и верный `SUPABASE_SERVICE_ROLE_KEY` |
