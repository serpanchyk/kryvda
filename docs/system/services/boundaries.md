# Service Boundaries

| Service | Current behavior | Future ownership |
| --- | --- | --- |
| API | Health, collection health, avatars, registry review, entity/channel profiles, filtered claims and source-post analysis | Waves and alerts |
| Telegram scraper | Pages sources through the Telegram gateway, persists posts/avatars and enqueues deterministic registry matches | Collection and target-filtered job handoff |
| Telegram gateway | Stateless HTTP access to Telegram MTProto with the dedicated session; deployed on Vercel outside the department firewall | Telegram access only; no database |
| AI worker | Three-pass inference v3, entity resolution, candidates and persistence | Later deterministic aggregation |
| Frontend | Editorial Кривда overview, entity/channel profiles, claims, evidence, split source-post analysis and shareable PNG chart cards | Registry administration |
| monitoring-common | Settings, logging, v3 schemas, validators and alias matcher | Cross-boundary contracts |

The gateway is deliberately independent of workspace packages so Vercel can build its directory
alone. Its wire contract lives in `telegram_monitor_gateway.contract` and is mirrored in the
scraper's `gateway_client`; `test_scraper_contract.py` runs the scraper client against the real
gateway application to keep both sides compatible.
