# syntax=docker/dockerfile:1.7
# Build context: repository root (needs packages/seed).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app/apps/api

FROM base AS deps
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

FROM base AS runtime
RUN useradd --create-home --uid 10001 app && mkdir -p /data/storage && chown app /data/storage
COPY --from=deps /opt/venv /opt/venv
COPY packages/seed /app/packages/seed
COPY apps/api/alembic.ini ./
COPY apps/api/migrations ./migrations
COPY apps/api/app ./app
ENV PATH="/opt/venv/bin:$PATH" \
    LOG_JSON=true \
    LOCAL_STORAGE_DIR=/data/storage \
    PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
