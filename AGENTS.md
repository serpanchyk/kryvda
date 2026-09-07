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

## Validation Guardrails

- Run `uv run pre-commit run --all-files` immediately after adding or substantially changing
  Python modules, not only at the end. It enforces a 100-character limit, including long SQL
  and string literals; if a hook reformats files, rerun the full hook suite before continuing.
- Treat strict mypy and runtime imports as separate checks. In particular, verify third-party
  annotations at runtime: a type accepted by mypy may not be subscriptable or otherwise valid
  in the installed library version. Instantiate Pydantic settings in a way that satisfies mypy
  when required environment-backed fields are declared.
- Add focused tests together with every new production module, then run `uv run pytest` before
  adding more scope. The repository enforces 80% total coverage, so account for the coverage
  effect of newly introduced runtime-boundary code and use typed fakes for external services.
