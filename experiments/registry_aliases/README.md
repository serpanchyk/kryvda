# Registry aliases v2

Telegram channels name registry entities in Ukrainian and Russian, by abbreviation, colloquially
(«Банкова», «Уряд», «Рада»), by nickname or insult («Зеля», «Порох») and by collective forms of
members («набушники», «порошенковцы»). Before v2 the alias prefilter caught 86.5% of the
annotated mentions on the measure-only golden test split; a missed mention silently drops the
post from analysis.

`work/` (DVC) holds the four per-entity proposal batches (`out*.json`, each alias with an
ambiguity level), the dev mentions the old aliases missed, and a 3,000-post sample of stored
revisions. Claude subagents generated the proposals from the current aliases and the missed dev
forms; the owner kept every level, and only «Буда» was excluded because its case forms include
the common word «буде».

| | Before | After |
|---|---|---|
| Test-split mentions matched | 346/400 (86.5%) | 396/400 (99.0%) |
| Sampled posts passing the prefilter | 799/3000 | 1147/3000 |
| Post x entity candidates | 1163 | 1898 |

```bash
uv run python experiments/registry_aliases/build_migration.py   # writes migration 015
uv run python experiments/registry_aliases/alias_recall.py infra/postgres/init/003_registry_seed.sql
uv run python experiments/registry_aliases/alias_recall_heldout.py infra/postgres/init/003_registry_seed.sql
uv run python experiments/registry_aliases/volume.py experiments/registry_aliases/work/sample_posts.jsonl
```

Two matcher changes ship with the aliases. The implicit person surname now comes only from the
canonical name, because descriptive (`мер Києва`) and reversed (`Корецький Сергій`) aliases
turned «Києва» and «Сергій» into surnames. One surface form may name several entities
(`Кравченко`, `Клименко`, `Генпрокурор`); the candidates pass decides which one a post means.
