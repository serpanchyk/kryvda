#!/bin/sh
# Daily PostgreSQL dump with retention, run by the Compose `backup` service.
set -eu

retention_days="${BACKUP_RETENTION_DAYS:-14}"

while true; do
  target="/backups/kryvda-$(date -u +%Y-%m-%dT%H%M%SZ).dump"
  if pg_dump --format=custom --file="${target}.partial"; then
    mv "${target}.partial" "${target}"
    echo "backup written: ${target}"
  else
    rm -f "${target}.partial"
    echo "backup failed" >&2
  fi
  find /backups -name 'kryvda-*.dump' -mtime "+${retention_days}" -delete
  sleep 86400
done
