# ЖерБақылау

Цифровой мониторинг земель, двусторонний сервис:

- **Веб-панель инспектора**: GIS-карта участков, жизненный цикл нарушений, фотофиксация, дедлайны, дашборд, спутниковый NDVI-слой.
- **Telegram-бот для граждан**: статус заявлений, база знаний, «Народный контроль» с геолокацией и фото. Интерфейс на русском и казахском.

Сквозной цикл: житель отправляет фото и точку → сигнал мгновенно появляется на карте → инспектор меняет статус → житель получает уведомление на своём языке.

> Прод-ссылки и скриншоты появятся после деплоя (Фаза 5). План работ — `docs/PLAN.md`, решения — `docs/DECISIONS.md`.

## Стек

| Слой | Технологии |
|---|---|
| API + бот | Python 3.12, FastAPI, SQLAlchemy 2 (async) + GeoAlchemy2, Alembic, Pydantic v2, aiogram 3, APScheduler |
| БД | PostgreSQL 15 + PostGIS (Supabase на проде, Docker локально) |
| Web | React 18, TypeScript, Vite, MapLibre GL, Tailwind, TanStack Query, Zustand, i18next |
| Инфраструктура | Supabase (БД, Auth, Storage, Realtime), Railway (API + бот), Vercel (web), Upstash Redis (FSM бота) |

## Быстрый старт

Нужны Docker, [uv](https://docs.astral.sh/uv/) и Node.js 20+.

### macOS / Linux

```bash
make setup          # зависимости + .env из .env.example
make up             # PostGIS + Redis + API в Docker; миграции и сид выполнятся сами
make dev-web        # панель: http://localhost:5173  (inspector@jer.kz / demo12345)
```

API: http://localhost:8000, документация OpenAPI: http://localhost:8000/docs.

### Windows

Рекомендуется WSL2 + Docker Desktop (интеграция с WSL включена). Внутри WSL команды те же, что для macOS.
Без WSL и make (PowerShell):

```powershell
Copy-Item .env.example .env
docker compose up -d --build
cd apps/web; npm ci; npm run dev
```

Все цели Makefile имеют эквивалент без make, таблица команд — в `CLAUDE.md`.

## Разработка

```bash
make db             # только PostGIS + Redis
make dev-api        # API на хосте с hot reload
make test           # pytest + vitest
make lint           # ruff, mypy, eslint, prettier
make gen-types      # OpenAPI → apps/web/src/api/schema.d.ts
make e2e            # сквозной smoke-тест цикла против запущенного API
make demo-reset     # вернуть демо-данные в исходное состояние
```

## Структура

```
apps/api        FastAPI + Telegram-бот + планировщик
apps/web        React-панель инспектора
packages/seed   участки (GeoJSON), заявления, сигналы, база знаний, импорт данных организаторов
supabase        SQL: RLS, Realtime, Storage
scripts         кроссплатформенные скрипты (сид, сброс, e2e, генерация типов, вебхук)
docs            план, решения, архитектура, деплой, сценарий демо
```

## Данные

Все участки, заявления и имена вымышлены. Регион — окрестности Тараза (Жамбылская область). Нормативный контент бота требует сверки с актуальным регламентом, казахские тексты — вычитки носителем языка (`docs/DECISIONS.md`).
