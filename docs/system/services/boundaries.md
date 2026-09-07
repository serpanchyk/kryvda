# Service Boundaries

| Service | Current behavior | Future ownership |
| --- | --- | --- |
| API | `/health`, read-only collection health | Posts, entities, channels, claims, timelines, statistics, waves, alerts |
| Telegram scraper | Collects the fixed approved channel pool | Authenticate, persist raw posts/revisions and lease AI jobs |
| AI worker | Idle process | Extract entities/stance/claims and resolve canonical entities |
| Frontend | Static shell | Browse analysis and manage entity registry |
| monitoring-common | Settings and logging | Shared contracts that do not belong to one boundary |
