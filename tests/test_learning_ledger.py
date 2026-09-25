import pytest

from sare_lotofacil.analysis.learning_ledger import build_learning_ledger


def _report(contest, hits, misses, omitted):
    return {
        "contest_number": contest,
        "hits": hits,
        "selected_misses": misses,
        "omitted_winners": omitted,
        "primary_delta_brier_vs_uniform": 0.0,
        "self_analysis": {"process_findings": ["auditado"], "adjustments_suggested": ["acumular evidência"]},
    }


def test_learning_ledger_tracks_target_gap_and_recurring_errors():
    reports = {"reports": [
        _report(3785, 11, [2, 4, 5, 10], [1, 3, 7, 9]),
        _report(3786, 12, [2, 5, 10], [3, 7, 9]),
    ]}
    ledger = build_learning_ledger(reports)
    assert ledger["objective"]["target"] == 15
    assert ledger["latest_entry"]["gap_to_15"] == 3
    assert ledger["summary"]["selected_miss_frequency"][0] == {"number": 2, "count": 2}
    assert ledger["learning_policy"]["single_contest_retuning_allowed"] is False
    assert ledger["learning_policy"]["challenger_requires_predeclared_prospective_validation"] is True


def test_learning_ledger_rejects_hits_outside_card_bounds():
    with pytest.raises(ValueError, match="LEARNING_LEDGER_HITS_OUT_OF_RANGE"):
        build_learning_ledger({"reports": [_report(3787, 16, [], [])]})
