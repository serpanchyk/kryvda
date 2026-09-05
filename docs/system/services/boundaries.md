# Service Boundaries

| Service | Current behavior | Future ownership |
| --- | --- | --- |
| API | `/health` only | Posts, entities, channels, claims, timelines, statistics, waves, alerts |
| Telegram scraper | Idle process | Authenticate, collect the agreed channels, persist raw posts |
| AI worker | Idle process | Extract entities/stance/claims and resolve canonical entities |
| Frontend | Static shell | Browse analysis and manage entity registry |
| monitoring-common | Settings and logging | Shared contracts that do not belong to one boundary |
