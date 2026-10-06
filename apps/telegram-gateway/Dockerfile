FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY packages/monitoring-common/pyproject.toml ./packages/monitoring-common/pyproject.toml
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/telegram-scraper/pyproject.toml ./apps/telegram-scraper/pyproject.toml
COPY apps/telegram-gateway/pyproject.toml ./apps/telegram-gateway/pyproject.toml
COPY apps/ai-worker/pyproject.toml ./apps/ai-worker/pyproject.toml
COPY apps/telegram-gateway/src ./apps/telegram-gateway/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package telegram-monitor-gateway

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /opt/venv /app/.venv
COPY apps/telegram-gateway/src ./src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/src"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
CMD ["python", "-m", "uvicorn", "telegram_monitor_gateway.asgi:app", "--host", "0.0.0.0", "--port", "8080"]
