# API

Полная интерактивная документация: **`/docs`** (Swagger UI) на любом запущенном API; схема — `apps/api/openapi.json`
(коммитится, фронт генерирует из неё `apps/web/src/api/schema.d.ts` командой `make gen-types`).

Все ошибки: `{"error": {"code", "message", "details"}}`. Авторизация инспектора — `Authorization: Bearer <JWT>`
(Supabase Auth; локально — `POST /api/v1/auth/login`). Служебные эндпоинты — заголовок `X-Service-Key`.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | БД, Redis, режим бота, хранилище |
| GET | `/api/v1/auth/config` · POST `/auth/login` · GET `/auth/me` | режим входа, локальный вход, текущий инспектор |
| GET | `/api/v1/parcels` | GeoJSON FeatureCollection; `bbox`, `status[]`, `violation_type[]`, `purpose[]`, `overdue` |
| GET | `/api/v1/parcels/search?q=` | поиск по кадастровому номеру / адресу |
| GET · PATCH | `/api/v1/parcels/{id}` | карточка (фото, сигналы, история, допустимые переходы) · дедлайн |
| POST | `/api/v1/parcels/{id}/transitions` | смена статуса; `409 INVALID_TRANSITION` со списком допустимых |
| POST | `/api/v1/parcels/{id}/photos` | multipart, до 10 фото, EXIF-координаты |
| GET | `/api/v1/parcels/{id}/act.pdf?lang=ru\|kk` | акт осмотра |
| GET | `/api/v1/parcels/{id}/cadastre` | сверка с реестром (адаптер ГБД ЗКС, демо) |
| GET | `/api/v1/signals` · `/signals/{id}` | очередь сигналов (открытые сверху), детали с дубликатами |
| POST | `/api/v1/signals/{id}/transitions` | в работу / подтвердить (участок → VIOLATION) / отклонить; житель уведомляется |
| GET · POST | `/api/v1/applications` · `/applications/{id}/transitions` | заявления; пояснения RU+KZ → пуш подписчикам |
| GET | `/api/v1/stats/dashboard` | KPI, сигналы по дням, типы нарушений, ближайшие сроки |
| GET · POST | `/api/v1/satellite/ndvi` · `/satellite/scan` | NDVI-слой, ручной запуск скана |
| GET | `/api/v1/export/parcels.geojson` · `.csv` | экспорт |
| GET | `/api/v1/events?since=` | лента событий (fallback для Realtime) |
| POST | `/api/v1/dev/simulate-signal` · `/dev/demo-reset` | 🔑 эмуляция сигнала из бота, сброс демо |
| POST | `/tg/webhook` | вебхук Telegram (секрет в заголовке) |
