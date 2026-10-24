"""Build migration 015 from the generated alias proposals in ``work/out*.json``.

Every proposal is kept except those in ``EXCLUDED`` and those already in the registry seed.
The migration also lets one surface form name several entities (``Кравченко``), since the
candidates pass decides which one a post means.

Usage:
    uv run python experiments/registry_aliases/build_migration.py
"""

from __future__ import annotations

import json
from pathlib import Path

WORK = Path("experiments/registry_aliases/work")
SEED = Path("infra/postgres/init/003_registry_seed.sql")
VERSION = "015_registry_aliases.sql"
# Aliases whose case forms collide with common words (``Буда`` inflects to ``буде``).
EXCLUDED = {("Кирило Буданов", "Буда")}
# Generic words, titles, bare first names and very short abbreviations (2026-10-24): they admit
# registry entities that posts mention only as background, which cost v4.8 precision 0.78 -> 0.70.
GENERIC = {
    "Рада",
    "парламент",
    "армія",
    "армия",
    "військові",
    "военные",
    "Сили оборони",
    "поліція",
    "полиция",
    "поліцейські",
    "полицейские",
    "копи",
    "копы",
    "менти",
    "менты",
    "мусора",
    "поліцаї",
    "Уряд",
    "Правительство",
    "урядовці",
    "Офіс",
    "Офис",
    "Бюро",
    "Розвідка",
    "Разведка",
    "міністр оборони",
    "министр обороны",
    "нардепи",
    "нардепы",
    "Контора",
    "ЄС",
    "«ЄС»",
    "ЕС",
    "«ЕС»",
    "Голос",
    "«Голос»",
    "Батьківщина",
    "слуги",
    "зелені",
    "зеленые",
    "Межа",
    "«Межа»",
    '"Межа"',
    "ЗМІНА",
    "«Зміна»",
    "Свобода",
    "Слідство",
    "Дзеркало",
    "Тексты",
    "Общественное",
    "ВС",
    "КС",
    "ГШ",
    "АП",
    "ДТ",
    "CES",
    "ИМИ",
    "ИЗИ",
    "SAP",
    "СІЧ",
    "Президент",
    "Гарант",
    "Зе",
    "Вова",
    "Зелений",
    "Зелёный",
    "Руслан",
    "Семен",
    "Семён",
    "Рустем",
    "Севгіль",
    "Севгиль",
    "Генпрокурор",
    "Генеральний прокурор",
    "Генеральный прокурор",
    "спікер",
    "спикер",
    "Главком",
    "Головком",
    "прем'єрка",
    "прем'єр-міністерка",
    "Хмара",
    "Боровик",
    "Ткач",
    "Матвиенко",
}

HEADER = """-- Registry aliases v2: Russian names, abbreviations, colloquial names, nicknames and
-- insulting names for every registry entity, generated per entity and reviewed by ambiguity
-- (experiments/registry_aliases). One surface form may now name several entities (Кравченко,
-- Клименко, Генпрокурор); the candidates pass decides which one a post means.
ALTER TABLE entity_aliases DROP CONSTRAINT IF EXISTS entity_aliases_normalized_alias_key;
ALTER TABLE entity_aliases DROP CONSTRAINT IF EXISTS entity_aliases_entity_normalized_alias_key;
ALTER TABLE entity_aliases
    ADD CONSTRAINT entity_aliases_entity_normalized_alias_key
    UNIQUE (entity_id, normalized_alias);

CREATE TEMP TABLE registry_alias_additions (canonical_name TEXT, alias TEXT);

COPY registry_alias_additions (canonical_name, alias) FROM stdin;
"""

FOOTER = """\\.

INSERT INTO entity_aliases (entity_id, alias, normalized_alias)
SELECT entity.id,
       trim(addition.alias),
       lower(regexp_replace(trim(addition.alias), '[[:space:]]+', ' ', 'g'))
FROM registry_alias_additions AS addition
JOIN registry_entities AS entity ON entity.canonical_name = addition.canonical_name
ON CONFLICT DO NOTHING;

DROP TABLE registry_alias_additions;
"""


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def seed_aliases() -> dict[str, set[str]]:
    copy = SEED.read_text(encoding="utf-8").split("FROM stdin;\n", 1)[1].split("\n\\.\n", 1)[0]
    existing: dict[str, set[str]] = {}
    for line in copy.splitlines():
        name, _, raw = line.split("\t")
        existing[name] = {normalize(name), *(normalize(a) for a in raw.split(";") if a.strip())}
    return existing


def additions() -> list[tuple[str, str]]:
    existing = seed_aliases()
    rows: list[tuple[str, str]] = []
    for path in sorted(WORK.glob("out*.json")):
        for name, proposals in json.loads(path.read_text(encoding="utf-8")).items():
            if name not in existing:
                raise ValueError(f"{path.name}: unknown registry entity {name!r}")
            for proposal in proposals:
                alias = " ".join(str(proposal["alias"]).split())
                key = normalize(alias)
                excluded = (name, alias) in EXCLUDED or alias in GENERIC
                if not alias or excluded or key in existing[name]:
                    continue
                if "\t" in alias or "\\" in alias:
                    raise ValueError(f"{name}: alias {alias!r} cannot be copied")
                existing[name].add(key)
                rows.append((name, alias))
    return rows


def main() -> None:
    rows = additions()
    body = HEADER + "".join(f"{name}\t{alias}\n" for name, alias in rows) + FOOTER
    Path("infra/postgres/migrations", VERSION).write_text(body, encoding="utf-8")
    Path("infra/postgres/init", VERSION).write_text(
        body
        + f"\nINSERT INTO schema_migrations (version)\nVALUES ('{VERSION}')\n"
        + "ON CONFLICT (version) DO NOTHING;\n",
        encoding="utf-8",
    )
    print(f"{VERSION}: {len(rows)} aliases")


if __name__ == "__main__":
    main()
