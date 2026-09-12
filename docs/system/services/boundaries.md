# Service Boundaries

| Service | Current behavior | Future ownership |
| --- | --- | --- |
| API | Health, collection health, avatars, entity registry and candidate review | Claims, timelines, statistics, waves, alerts |
| Telegram scraper | Collects sources and enqueues deterministic registry matches | Collection and target-filtered job handoff |
| AI worker | Three-pass inference v3, entity resolution, candidates and persistence | Later deterministic aggregation |
| Frontend | Static shell | Browse analysis and manage entity registry |
| monitoring-common | Settings, logging, v3 schemas, validators and alias matcher | Cross-boundary contracts |
