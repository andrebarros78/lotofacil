from types import SimpleNamespace

import pytest

from scripts import github_operational_cycle as cycle
from scripts import verify_github_operational_state as audit
from scripts import verify_third_party_history as history


def _prediction_with_primary_card() -> dict[str, object]:
    prediction = {
        "target_contest": 3781,
        "created_at_utc": "2026-09-16T06:16:28+00:00",
        "training_last_contest": 3780,
        "training_snapshot_hash": "snapshot-hash",
        "protocol_hash": "protocol-hash",
        "models": {"M0_uniform": [0.6], "M1_frequency_regularized_lambda_100": [0.61], "M2_exponential_alpha_0.05": [0.59]},
        "primary_card": {"target_contest": 3781, "card": list(range(1, 16))},
    }
    prediction["prediction_sha256"] = cycle._sha256(cycle._prediction_hash_payload(prediction))
    return prediction


def test_operational_auditor_uses_same_primary_card_hash_contract_as_producer() -> None:
    prediction = _prediction_with_primary_card()
    assert audit._prediction_hash_payload(prediction) == cycle._prediction_hash_payload(prediction)
    assert audit._sha256(audit._prediction_hash_payload(prediction)) == prediction["prediction_sha256"]


def test_operational_auditor_preserves_legacy_hash_contract_without_primary_card() -> None:
    prediction = _prediction_with_primary_card()
    prediction.pop("primary_card")
    assert "primary_card" not in audit._prediction_hash_payload(prediction)
    assert audit._prediction_hash_payload(prediction) == cycle._prediction_hash_payload(prediction)


def test_third_party_one_contest_lag_becomes_explicit_trailing_official_patch() -> None:
    records = [SimpleNamespace(contest_id=index) for index in range(1, 3780)]
    internal, trailing, patches = history._official_patch_ids(records, 3780)
    assert internal == []
    assert trailing == [3780]
    assert patches == [3780]


def test_third_party_internal_and_trailing_gaps_are_both_explicit() -> None:
    records = [SimpleNamespace(contest_id=index) for index in range(1, 10) if index != 5]
    internal, trailing, patches = history._official_patch_ids(records, 10)
    assert internal == [5]
    assert trailing == [10]
    assert patches == [5, 10]


def test_third_party_source_ahead_of_official_fails_closed() -> None:
    records = [SimpleNamespace(contest_id=index) for index in range(1, 11)]
    with pytest.raises(RuntimeError, match="ahead of official"):
        history._official_patch_ids(records, 9)
