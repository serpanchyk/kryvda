"""Tests for the direct post x entity prototype."""

import json
from typing import Any

from mamay_direct import direct_rows, grounded, verify_answer
from telegram_monitor_ai_worker.models import ModelResponse

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


class VerdictClient:
    """Answer every verification with fixed verdicts per quote ID."""

    def __init__(self, verdicts: dict[str, str]) -> None:
        self.verdicts = verdicts
        self.calls = 0

    async def _request(self, name: Any, messages: Any, tokens: int, schema: Any) -> ModelResponse:
        self.calls += 1
        quotes = schema["properties"]["quotes"]["required"]
        payload = {
            "quotes": {q: {"reason": "", "actor": "", "link": self.verdicts[q]} for q in quotes}
        }
        return ModelResponse(json.dumps(payload), 1)


async def test_verify_answer_keeps_confirmed_quotes_and_drops_unchecked_stances() -> None:
    answer = {
        "attacked": True,
        "attacks": [
            {
                "quote": "НАБУ знову провалилося.",
                "source_kind": "канал",
                "source": "",
                "rhetoric": [],
            },
            {
                "quote": "СБУ затримала агента.",
                "source_kind": "канал",
                "source": "",
                "rhetoric": [],
            },
        ],
        "praised": True,
        "praises": [{"quote": "вигадано", "source_kind": "канал", "source": ""}],
    }
    client = VerdictClient({"q1": "колишній працівник чи член сутності", "q2": "інший актор"})
    attempts: list[Any] = []

    verified = await verify_answer(client, TEXT, {**ENTITY, "mentions": ["НАБУ"]}, answer, attempts)  # type: ignore[arg-type]

    assert verified["attacked"] is True
    assert [item["quote"] for item in verified["attacks"]] == ["НАБУ знову провалилося."]
    assert verified["praised"] is False
    assert client.calls == 1
    assert attempts[0]["status"] == "valid"
