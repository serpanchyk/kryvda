#!/bin/sh
set -eu
umask 077
target="/backups/kryvda-$(date -u +%Y-%m-%dT%H%M%SZ).dump"
trap 'rm -f "${target}.partial"' EXIT
pg_dump --format=custom --file="${target}.partial"
mv "${target}.partial" "${target}"
find /backups -name 'kryvda-*.dump' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
