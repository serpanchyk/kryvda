"""Tests for the direct post x entity prototype."""

from mamay_direct import direct_rows, grounded

TEXT = "Канал пише: НАБУ   знову провалилося. СБУ затримала агента."
ENTITY = {"id": "e1", "canonical_name": "НАБУ"}


def test_grounded_ignores_whitespace_but_not_invented_text() -> None:
    assert grounded("НАБУ знову провалилося.", TEXT)
    assert not grounded("НАБУ працює добре.", TEXT)
    assert not grounded("  ", TEXT)


def test_direct_rows_turn_quotes_into_evidence_claims_and_stances() -> None:
    answer = {
        "attacked": True,
        "attacks": [
            {
                "quote": "НАБУ знову провалилося.",
                "source_kind": "канал",
                "source": "",
                "rhetoric": ["делегітимізація"],
            },
            {"quote": "вигадана цитата", "source_kind": "канал", "source": "", "rhetoric": []},
        ],
        "praised": True,
        "praises": [],
    }

    claims, rows = direct_rows(ENTITY, answer, TEXT, 2)

    assert [claim["id"] for claim in claims] == ["c3", "c4"]
    assert claims[0]["attribution"]["source_kind"] == "channel_editorial"
    assert [(row["stance"], row["rhetoric"]) for row in rows] == [
        ("негативне", ["делегітимізація"]),
        ("позитивне", []),
    ]
    assert claims[1]["evidence_text"] == ""
