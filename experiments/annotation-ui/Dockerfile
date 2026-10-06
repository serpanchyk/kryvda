FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY experiments/annotation-ui/web/package*.json ./
RUN npm ci
COPY experiments/annotation-ui/web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/ai-worker/pyproject.toml apps/ai-worker/pyproject.toml
COPY apps/telegram-scraper/pyproject.toml apps/telegram-scraper/pyproject.toml
COPY apps/telegram-gateway/pyproject.toml apps/telegram-gateway/pyproject.toml
COPY packages/monitoring-common/pyproject.toml packages/monitoring-common/pyproject.toml
RUN uv sync --frozen --only-group annotation --no-install-workspace
COPY experiments/annotation-ui/src/ experiments/annotation-ui/src/
COPY experiments/datasets/golden_v0/annotation_schema_v1.json \
    experiments/datasets/golden_v0/annotation_import_schema_v1.json \
    experiments/datasets/golden_v0/
COPY experiments/datasets/golden_v0/src/ experiments/datasets/golden_v0/src/
COPY --from=frontend /web/dist /static
ENV PYTHONPATH=/workspace/experiments/annotation-ui/src:/workspace/experiments/datasets/golden_v0/src
ENV ANNOTATION_STATIC=/static
CMD ["/workspace/.venv/bin/uvicorn", "annotation_app:app", "--host", "0.0.0.0", "--port", "8090"]
