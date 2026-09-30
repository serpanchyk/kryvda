@AGENTS.md

## Orientation

- Read `docs/CURRENT_STATE.md` first for the current runtime state; architecture lives in
  `docs/system/`, domain vocabulary in `docs/CONTEXT.md`, commands in `docs/run-project.md`.
- Communicate with the user in Ukrainian unless asked otherwise.

## Local Runtime

- Start or rebuild the stack: `docker compose up -d --build`; stop: `docker compose stop`.
- Endpoints: frontend `http://localhost:5173`, API `http://localhost:8000` (`/health`),
  PostgreSQL on host port `5433` (host port `5432` is taken by an unrelated `shkandal` project).
- The scraper and AI worker loop on `Restarting` when the `postgres` service is down; start the
  stack rather than debugging them individually.
- Frontend lives in `apps/frontend` (Vite + React + Tailwind + shadcn); run
  `(cd apps/frontend && npm ci && npm run lint && npm run test && npm run build)` when it changes.
