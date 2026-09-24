# CLAUDE.md — правила проекта «ЖерБақылау»

Сервис мониторинга земель: веб-панель инспектора (React + MapLibre) и Telegram-бот для граждан (aiogram 3), общий бэкенд FastAPI + PostGIS (Supabase).
Полное ТЗ: `PROMPT_Claude_Code_ZemKontrol.md`. План и фазы: `docs/PLAN.md`. Решения: `docs/DECISIONS.md`.

## Язык
- Общение с командой, документация и коммиты (описательная часть) — на русском. Идентификаторы в коде — на английском.
- Любой пользовательский текст идёт только через локализацию: веб — `apps/web/src/locales/{ru,kk}.json`, бот и уведомления — `apps/api/app/locales/{ru,kk}/*.ftl` (Fluent), нормативный контент — `packages/seed/knowledge/{ru,kk}/`. Хардкод строк в UI/боте запрещён.

## Структура
```
apps/api          FastAPI + aiogram-бот + APScheduler (один процесс)
  app/api         роуты (тонкие, без бизнес-логики)
  app/domain      enum'ы, машина состояний, чистая логика
  app/services    бизнес-логика (используют и API, и бот)
  app/db          модели SQLAlchemy, сессии
  app/providers   адаптеры: cadastre, satellite, notification, storage
  app/bot         хендлеры, клавиатуры, FSM
  app/locales     Fluent-локали бота и уведомлений (ru, kk)
  app/seed        генератор участков, загрузчик сида, импорт GeoJSON организаторов
  app/workers     APScheduler (спутниковый скан)
  migrations      Alembic
  tests
apps/web          React 18 + Vite + TS
  src/api         клиент + сгенерированный schema.d.ts (не редактировать руками)
packages/seed     GeoJSON, заявления, база знаний, organizers/
supabase          SQL: RLS, realtime publication, бакеты
scripts           кроссплатформенные Python-скрипты (seed, demo_reset, e2e_smoke, set_webhook, gen_types)
docs              PLAN, DECISIONS, ARCHITECTURE, API, DEPLOY, DEMO_SCRIPT
```

## Зоны ответственности
Сейчас проект ведёт один человек, но зоны сохраняются, чтобы второй мог подключиться и чтобы параллельные субагенты не конфликтовали:
- **A (web):** `apps/web/**`, деплой Vercel. Не трогает `apps/api`, кроме чтения `openapi.json`.
- **B (backend+bot):** `apps/api/**`, `packages/seed/**`, `supabase/**`, `scripts/**`, деплой Railway/Supabase.
- **Общее (меняется только осознанно, с записью в `docs/DECISIONS.md`):** контракт API (`apps/api/openapi.json`, `apps/web/src/api/schema.d.ts`), корневые конфиги, `docs/`.
- Субагент, работающий в зоне A или B, не редактирует файлы другой зоны. Если нужно изменить контракт, он останавливается и сообщает об этом.

## Команды
Все цели Makefile продублированы Python-скриптами для Windows без make.
| Действие | make | без make |
|---|---|---|
| Поднять всё (PostGIS+Redis+API) | `make up` | `docker compose up -d --build` |
| Только БД и Redis (API на хосте) | `make db` | `docker compose up -d db redis` |
| API локально (hot reload) | `make dev-api` | `cd apps/api && uv run uvicorn app.main:app --reload` |
| Web локально | `make dev-web` | `cd apps/web && npm run dev` |
| Миграции | `make migrate` | `cd apps/api && uv run alembic upgrade head` |
| SQL Supabase (RLS/realtime/bucket) | `make supabase-sql` | `uv run --project apps/api python scripts/apply_supabase_sql.py` |
| Сид (если БД пустая) | `make seed` | `uv run --project apps/api python scripts/seed.py` |
| Сброс демо | `make demo-reset` | `uv run --project apps/api python scripts/demo_reset.py [--base-url URL]` |
| Тесты | `make test` | `cd apps/api && uv run pytest` ; `cd apps/web && npm test` |
| Линт | `make lint` | `cd apps/api && uv run ruff check . && uv run mypy app` ; `cd apps/web && npm run lint && npm run typecheck` |
| Типы API для фронта | `make gen-types` | `uv run --project apps/api python scripts/gen_types.py` |
| E2E smoke | `make e2e BASE_URL=…` | `uv run --project apps/api python scripts/e2e_smoke.py --base-url http://localhost:8000` |

Тесты API создают отдельную БД `<db>_test` на том же сервере PostGIS (нужен `make db`).
После любого изменения схем Pydantic или роутов: `make gen-types` и закоммитить `openapi.json` + `schema.d.ts` (CI проверяет).

## Соглашения
- **Git:** `main` защищена; ветки `feat/web-*`, `feat/api-*`, `fix/*`, `docs/*`. Conventional commits (`feat(api): …`, `fix(web): …`). PR маленькие.
- **Фаза считается закрытой**, только когда тесты и линтеры зелёные, DoD из `docs/PLAN.md` выполнен и есть коммит. При красных тестах дальше не идём.
- **Проверяй, а не предполагай:** API — curl/httpie, UI — сборка + скриншоты Playwright.
- **Python:** 3.12, uv, типизация везде, Pydantic v2 на границах, async SQLAlchemy 2, structlog. Роуты тонкие, логика в `services`. Ошибки — через доменные исключения → единый формат `{error:{code,message,details}}`.
- **Гео:** координаты хранятся только в PostGIS (SRID 4326). Площади и расстояния считаем через `::geography`. Никакого SQLite.
- **Статусы** меняются только через `app/domain/state_machine.py`. Каждый переход пишет `status_transitions` и `events` в одной транзакции.
- **TS:** strict, без `any`; серверное состояние в TanStack Query, UI-состояние в Zustand; типы только из `schema.d.ts`.
- **Кроссплатформенность:** LF (`.gitattributes`), `pathlib`, никаких bash-only скриптов в критическом пути.

## Секреты
- Только в `.env` (корень) и в переменных Railway/Vercel. В git лежит `.env.example` с описанием переменных.
- `SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_BOT_TOKEN`, `SERVICE_API_KEY`, `TELEGRAM_WEBHOOK_SECRET` никогда не попадают во фронтенд и в git. Во фронт идут только `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- Шаги, требующие логина (Supabase, Railway, Vercel, Upstash, BotFather, gh), выполняет человек по командам из `docs/DEPLOY.md`. Авторизацию не обходим.

## Контент и данные
- Не выдумывать номера статей закона, реальные ПДн и реальные кадастровые номера. Нормативка помечается «требует сверки с актуальным регламентом», казахские тексты — «требует вычитки носителем языка».
- Демо-регион: окрестности Тараза (~42.90N, 71.37E), данные фиктивные.
- Не оставлять неработающих кнопок: незаконченное в UI не показываем.
