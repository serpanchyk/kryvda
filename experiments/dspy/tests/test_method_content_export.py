"""Tests for the «Як працює» content export."""

from __future__ import annotations

import pytest
from entity_stance_report import PostCounts
from method_content_export import VERSIONS, scores, spans


def test_spans_prefer_the_longest_form_and_list_every_occurrence() -> None:
    text = "Дарья Каленюк сказала. Потім Каленюк додала."

    assert spans(text, ["Каленюк", "Дарья Каленюк"]) == [
        {"start": 0, "end": 13},
        {"start": 29, "end": 36},
    ]


def test_scores_sum_counts_and_round_the_interval() -> None:
    counts = {"a": PostCounts(tp=3, fp=1, fn=0), "b": PostCounts(tp=1, fp=0, fn=2)}

    result = scores(counts, [0.5, 0.6, 0.7])

    assert result["tp"] == 4 and result["fp"] == 1 and result["fn"] == 2
    assert result["precision"] == pytest.approx(0.8)
    assert result["recall"] == pytest.approx(0.6667, abs=1e-4)
    assert result["f1_interval"] == [0.5, 0.6]


def test_versions_end_with_the_current_pipeline_scored_on_the_test_split() -> None:
    version, _, test_run, status, _ = VERSIONS[-1]

    assert (version, test_run, status) == ("4.9", "v49", "current")
    assert sum(entry[3] == "previous" for entry in VERSIONS) == 1
