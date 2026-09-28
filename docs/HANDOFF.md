# Передача проекта «ЖерБақылау»

Документ для разработчика, который продолжает проект. Что это за продукт и какие в нём функции, описано в [README](../README.md), куда двигаться дальше — в [ROADMAP](ROADMAP.md).

---

## 1. Что передать (делает текущий владелец)

Секреты **в git не лежат** и не должны туда попадать. Передавайте их только через менеджер паролей (1Password / Bitwarden) или зашифрованным файлом, не через чат.

| Что | Как дать доступ |
|---|---|
| Репозиторий `Nurrss/jer-baqylau` (приватный) | `gh api -X PUT repos/Nurrss/jer-baqylau/collaborators/<github-логин> -f permission=push`, либо Settings → Collaborators |
| Railway, проект `fretful-taste`, сервис `jer-api` | Project Settings → Members → Invite. ⚠️ В проекте есть чужой сервис `jihc_voice`, его не трогать |
| Vercel, проект `jer-baqylau` | Team → Members → Invite (или перенести проект в команду нового разработчика) |
| Supabase, проект `sxwzidgibjpzerwoorgb` (регион Сеул) | Organization → Team → Invite |
| Upstash Redis | Account → Team, либо просто передать `REDIS_URL` |
| Telegram-бот `@take_a_place_bot` | BotFather → `/mybots` → Transfer ownership, либо передать токен |
| Файл `.env.production` | Через менеджер паролей. В нём все прод-секреты (список ниже) |
| Учётка инспектора на проде | `inspector@jer.kz` + пароль из `.env.production` (`DEMO_INSPECTOR_PASSWORD`) |

**Секреты прода (только имена):** `DATABASE_URL`, `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SERVICE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `DEMO_INSPECTOR_PASSWORD`. Во фронтенд (Vercel) идут только `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

> После передачи желательно сменить `SERVICE_API_KEY`, `TELEGRAM_WEBHOOK_SECRET` и пароль инспектора, затем переустановить вебхук: `uv run --project apps/api python scripts/set_webhook.py` с `JER_ENV_FILE=.env.production`.

## 2. Где что работает

| Компонент | Где | Адрес |
|---|---|---|
| Веб-панель + прокси `/api/*` | Vercel | https://jer-baqylau.vercel.app |
| API + бот (вебхук) + планировщик, один контейнер | Railway, регион southeast-asia | https://jer-api-production.up.railway.app |
| PostgreSQL + PostGIS, Auth, Storage, Realtime | Supabase, Сеул, session pooler | — |
| Redis (FSM бота, блокировки задач спутника) | Upstash | — |
| Спутник | Earth Search (AWS), без ключа | `SATELLITE_PROVIDER=sentinel`, скан раз в 6 ч |

Панель обращается к API через тот же домен (`/api/*` → Railway, см. `apps/web/vercel.json`), потому что в некоторых сетях Казахстана `*.up.railway.app` не резолвится. Скрипты против прода тоже запускайте через `--base-url https://jer-baqylau.vercel.app`.

## 3. Первый день

```bash
git clone https://github.com/Nurrss/jer-baqylau.git && cd jer-baqylau
make setup                 # uv + npm зависимости, .env из .env.example
make up                    # PostGIS + Redis + API в Docker, миграции и сид сами
make dev-web               # http://localhost:5173, вход inspector@jer.kz / demo12345
make test && make lint     # должно быть зелёным: 87 тестов API + vitest, ruff, mypy, eslint
```

Дальше:
1. Пройдите тур в панели (кнопка `?` → «Обзор платформы») и сценарий из [DEMO_SCRIPT.md](DEMO_SCRIPT.md), включая блок «Честность».
2. Прочитайте [CLAUDE.md](../CLAUDE.md) (правила проекта), [ARCHITECTURE.md](ARCHITECTURE.md) и [DECISIONS.md](DECISIONS.md) (ADR-001…017).
3. Положите `.env.production` в корень репозитория (он в `.gitignore`) и проверьте прод:
   ```bash
   JER_ENV_FILE=.env.production uv run --project apps/api python scripts/e2e_smoke.py --base-url https://jer-baqylau.vercel.app
   JER_ENV_FILE=.env.production uv run --project apps/api python scripts/demo_reset.py --base-url https://jer-baqylau.vercel.app
   ```
   E2E меняет демо-данные, поэтому после него всегда делайте `demo_reset`.

## 4. Как вести разработку

- **Контракт API.** После любого изменения схем Pydantic или роутов запустите `make gen-types` и закоммитьте `apps/api/openapi.json` и `apps/web/src/api/schema.d.ts`. `schema.d.ts` руками не редактируется.
- **Тексты.** Только через локализации: веб — `apps/web/src/locales/{ru,kk}.json` (тест сверяет ключи), бот, уведомления и PDF — `apps/api/app/locales/{ru,kk}/*.ftl`.
- **Статусы** меняются только через `app/domain/state_machine.py` и `record_transition`: переход автоматически попадает в цепочку хешей журнала. Не пишите в `status_transitions` напрямую, иначе `GET /audit/verify` покажет «Журнал повреждён».
- **Миграции** (Alembic): у CHECK-ограничений enum'ов есть соглашение об именах, поэтому при пересоздании используйте `op.f("ck_…")`, иначе получится двойной префикс.
- **Коммиты**: Conventional Commits (`feat(api): …`, `fix(web): …`), описание на русском.
- **Claude Code**: `CLAUDE.md` загружается автоматически и содержит все правила. Зоны A (web) и B (api) можно вести параллельными агентами.

## 5. Деплой

```bash
# API (Railway): миграции применяются при старте контейнера
railway up --service jer-api --detach
railway logs --service jer-api          # проверить, что нет повторяющихся «Application startup complete»

# Веб (Vercel)
cd apps/web && vercel --prod

# Проверка
curl https://jer-baqylau.vercel.app/health
```

Полная инструкция с нуля (новые аккаунты) — в [DEPLOY.md](DEPLOY.md).

## 6. Подводные камни (узнали на практике)

| Проблема | Что знать |
|---|---|
| Railway игнорирует `railway.json` при сборке Railpack | Переменная `RAILWAY_DOCKERFILE_PATH=apps/api/Dockerfile` обязательна. Регион задаётся через `railway scale` |
| **Память на Railway 512 МБ**, API в покое ~400 МБ | Тяжёлые задачи (история спутника) идут строго по одной, в один поток, с `GDAL_CACHEMAX=32`. Попытка запоминается в Redis на 30 мин. Если увеличите параллельность, будут OOM-рестарты по кругу. Правильное решение — отдельный воркер (ROADMAP 2.1) |
| БД в Сеуле, API в Сингапуре: каждый запрос к БД ~150–200 мс | Никаких N+1: собирайте данные пакетными запросами. `pool_pre_ping` выключен намеренно |
| Токен бота общий для локальной среды и прода | Локально держите `BOT_MODE=disabled`, иначе локальный polling сбросит вебхук прода. Для разработки лучше завести отдельного бота |
| Тесты | Создают БД `<db>_test` на локальном PostGIS и **отказываются** работать с не-localhost БД без `TEST_DATABASE_URL`, чтобы случайно не стереть прод |
| Скрипты против прода | Нужен `JER_ENV_FILE=.env.production`. Ключи Supabase принимаются в старом (`anon`/`service_role`) и новом (`sb_publishable`/`sb_secret`) формате |
| Данные Sentinel-2 | Отражательная способность в Earth Search уже гармонизирована: заявленный offset −0.1 применяется, только если значения не уходят в минус (`effective_offset`) |
| Telegram Mini App `/app` | Telegram открывает Mini App только по HTTPS: кнопки появляются, когда `PUBLIC_WEB_URL` начинается с `https://` (на проде так и есть). Локально проверяйте в браузере, подставив подписанный `initData` (`app.core.telegram_webapp.sign_init_data`). Имя бота для ссылок — `VITE_TELEGRAM_BOT` (по умолчанию `take_a_place_bot`) |
| Страница владельца `/inspect` | Камера и геолокация работают только по HTTPS (на проде так и есть). В снимках с canvas нет EXIF, поэтому проверка `EXIF_GPS` = `skip` |
| React Compiler (eslint) | Нельзя вызывать `setState` синхронно в эффектах; используйте перемонтирование через `key` или колбэки |
| Supabase Auth | Открытая регистрация ещё включена: выключите «Allow new users to sign up». API защищён списком `INSPECTOR_EMAILS` |

## 7. Открытые задачи на ближайшее время

1. Выключить регистрацию в Supabase и сменить секреты после передачи (раздел 1).
2. Вычитка казахских текстов носителем языка (ROADMAP 1.1).
3. Вынести спутник и PDF в отдельный воркер (ROADMAP 2.1). Сейчас это самое узкое место прода.
4. Роли «инспектор / руководитель» и принцип четырёх глаз для принятия отчётов (ROADMAP 1.3).
5. Привязка существующих правообладателей к Telegram / eGov (ROADMAP 2.2) — сейчас ссылка сама уходит только тем, кто получил землю через Mini App.
