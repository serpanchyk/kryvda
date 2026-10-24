FROM postgres:16-alpine
COPY infra/postgres/init/ /docker-entrypoint-initdb.d/
COPY infra/postgres/ /database/
COPY scripts/migrate.sh /migrate.sh
COPY scripts/deploy/backup-once.sh /backup-once.sh
