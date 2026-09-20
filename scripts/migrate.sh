#!/bin/sh
set -eu

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?POSTGRES_USER must be set}" \
  -d "${POSTGRES_DB:?POSTGRES_DB must be set}" -f /database/migrate.sql
