from __future__ import annotations

import pytest

from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_report,
    build_post_contest_reports,
    render_post_contest_report_markdown,
)


def _prediction(*, stored_hits: int = 10) -> dict:
    return {
        "target_contest": 3784,
        "evaluation": {
            "observed_contest": 3784,
            "observed_numbers": [1, 2, 8, 10, 11, 12, 15, 16, 18, 19, 20, 21, 22, 24, 25],
            "delta_brier": {"M1_frequency_regularized_lambda_100": 0.0018128083156510044},
        },
        "primary_card": {
            "card": [1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 20, 22, 24, 25],
        },
        "primary_card_evaluation": {
            "hits": stored_hits,
            "observed_contest": 3784,
        },
    }
def test_constructive_report_contains_required_fields_and_self_analysis() -> None:
    report = build_post_contest_report(_prediction())

    assert report["status"] == "POST_CONTEST_REPORT_PASS"
    assert report["contest_number"] == 3784
    assert report["result_display"] == "01 02 08 10 11 12 15 16 18 19 20 21 22 24 25"
    assert report["generated_card_display"] == "01 02 03 04 05 10 11 12 13 14 15 20 22 24 25"
    assert report["hits"] == 10
    assert report["matched_numbers"] == [1, 2, 10, 11, 12, 15, 20, 22, 24, 25]
    assert report["selected_misses"] == [3, 4, 5, 13, 14]
    assert report["omitted_winners"] == [8, 16, 18, 19, 21]

    analysis = report["self_analysis"]
    assert analysis["corrections_required"]
    assert analysis["adjustments_suggested"]
    assert analysis["implementations_suggested"]
    assert any("baseline uniforme" in item for item in analysis["process_findings"])

    markdown = render_post_contest_report_markdown(report)
    assert "Concurso Número: 3784" in markdown
    assert "Número de acertos: 10" in markdown
    assert "## Autoanálise do processo" in markdown
    assert "### Correções necessárias" in markdown
    assert "### Ajustes sugeridos" in markdown
    assert "### Implementações necessárias" in markdown
def test_report_fails_closed_when_persisted_hit_count_is_inconsistent() -> None:
    with pytest.raises(RuntimeError, match="POST_CONTEST_HIT_MISMATCH"):
        build_post_contest_report(_prediction(stored_hits=9))


def test_legacy_evaluated_prediction_reports_process_gap_without_reconstruction() -> None:
    prediction = _prediction()
    prediction.pop("primary_card")
    prediction.pop("primary_card_evaluation")

    report = build_post_contest_report(prediction)

    assert report["status"] == "POST_CONTEST_REPORT_PASS_WITH_PROCESS_GAP"
    assert report["generated_card"] is None
    assert report["hits"] is None
    assert "PRIMARY_CARD_NOT_FROZEN_FOR_EVALUATED_CONTEST" in report["self_analysis"]["process_errors"]
    assert "NO_RETROACTIVE_CARD_RECONSTRUCTION" in report["guardrails"]


def test_report_ledger_is_ordered_and_exposes_latest() -> None:
    first = _prediction()
    first["target_contest"] = 3783
    first["evaluation"]["observed_contest"] = 3783
    first["primary_card_evaluation"]["observed_contest"] = 3783

    state = build_post_contest_reports({"predictions": [_prediction(), first]})

    assert state["report_count"] == 2
    assert [item["contest_number"] for item in state["reports"]] == [3783, 3784]
    assert state["latest_report"]["contest_number"] == 3784
