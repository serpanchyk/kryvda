# Agent Guide

## Purpose

Telegram Monitor tracks an agreed fixed channel pool for ЦПК. The target pipeline is raw
post collection, structured AI analysis, and later entity/claim aggregation.

## Boundaries

- `apps/api` owns the HTTP API boundary.
- `apps/telegram-scraper` owns Telegram collection.
- `apps/ai-worker` owns analysis execution.
- `packages/monitoring-common` owns shared runtime utilities and cross-boundary contracts.
- PostgreSQL is the sole runtime dependency and future job transport. Do not add Redis or a
  broker without an explicit architecture decision.

## Engineering Rules

- Keep business logic under package `src/` directories and preserve service ownership.
- Use typed async I/O at runtime boundaries and structured JSON logs; never use `print()`.
- Keep secrets out of git; document every setting in the appropriate `.env.example`.
- Use Docker Compose as the normal runtime path.
- Update `PROJECT_CONTEXT.md` and relevant `docs/system/` material whenever architecture,
  configuration, or runtime behavior changes.
- Commit all completed task changes before handing work back to the user.
- Before completion run `uv lock`, `uv sync --frozen --all-packages`, `uv run pre-commit run
  --all-files`, `uv run pytest`, and frontend checks when frontend files change. Report any
  skipped check and why.
