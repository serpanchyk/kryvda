# Run the Project

## Docker Compose

```bash
cp .env.example .env
cp infra/postgres/.env.example infra/postgres/.env
docker compose up --build
```

The API health endpoint is `http://localhost:8000/health`; the frontend is
`http://localhost:5173`.

## Local Checks

```bash
uv lock
uv sync --frozen --all-packages
uv run pre-commit run --all-files
uv run pytest
(cd apps/frontend && npm ci && npm run lint && npm run test && npm run build)
```
