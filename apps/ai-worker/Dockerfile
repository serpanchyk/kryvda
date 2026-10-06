FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY packages/monitoring-common/pyproject.toml ./packages/monitoring-common/pyproject.toml
COPY packages/monitoring-common/src ./packages/monitoring-common/src
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/telegram-scraper/pyproject.toml ./apps/telegram-scraper/pyproject.toml
COPY apps/telegram-gateway/pyproject.toml ./apps/telegram-gateway/pyproject.toml
COPY apps/ai-worker/pyproject.toml ./apps/ai-worker/pyproject.toml
COPY apps/ai-worker/src ./apps/ai-worker/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package telegram-monitor-ai-worker

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /opt/venv /app/.venv
COPY apps/ai-worker/src ./src
COPY apps/ai-worker/config.yaml ./config.yaml
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/src"
CMD ["python", "-m", "telegram_monitor_ai_worker.main"]
