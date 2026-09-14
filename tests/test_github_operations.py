from datetime import date, timedelta

import pytest

from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER
from scripts import github_operational_cycle as cycle


def _records(count: int = 5):
    base = date(2026, 1, 1)
    return tuple(
        validate_contest(index, base + timedelta(days=index), range(1, 16))
        for index in range(1, count + 1)
    )


def test_prediction_hash_detects_tampering():
    records = _records()
    prediction = cycle._build_prediction(6, "snapshot-hash", records, "2026-09-13T12:00:00+00:00")
    cycle.verify_prediction_hashes({"predictions": [prediction]})
    prediction["models"][cycle.PRIMARY_MODEL][0] += 0.001
    with pytest.raises(RuntimeError, match="prediction hash mismatch"):
        cycle.verify_prediction_hashes({"predictions": [prediction]})


def test_prediction_hash_covers_frozen_primary_card():
    records = _records()
    prediction = cycle._build_prediction(6, "snapshot-hash", records, "2026-09-13T12:00:00+00:00")
    assert prediction["primary_card"]["target_contest"] == 6
    assert len(prediction["primary_card"]["card"]) == 15
    prediction["primary_card"]["card"][0] = 25
    with pytest.raises(RuntimeError, match="prediction hash mismatch"):
        cycle.verify_prediction_hashes({"predictions": [prediction]})


def test_legacy_prediction_without_primary_card_keeps_old_hash_contract():
    records = _records()
    prediction = cycle._build_prediction(6, "snapshot-hash", records, "2026-09-13T12:00:00+00:00")
    prediction.pop("primary_card")
    prediction.pop("primary_card_evaluation")
    prediction["prediction_sha256"] = cycle._sha256(cycle._prediction_hash_payload(prediction))
    cycle.verify_prediction_hashes({"predictions": [prediction]})


def test_prediction_is_scored_only_after_result_and_keeps_uniform_oracle():
    records = _records(6)
    prediction = cycle._build_prediction(6, "snapshot-hash", records[:5], "2026-09-13T12:00:00+00:00")
    frozen_card = tuple(prediction["primary_card"]["card"])
    cycle._evaluate_prediction(prediction, records[5])
    assert prediction["evaluation"]["scores"]["M0_uniform"] == pytest.approx(UNIFORM_BRIER)
    assert prediction["training_last_contest"] == 5
    assert prediction["target_contest"] == 6
    assert prediction["primary_card_evaluation"]["hits"] == 15
    assert tuple(prediction["primary_card"]["card"]) == frozen_card
    cycle.verify_prediction_hashes({"predictions": [prediction]})


def test_prospective_summary_cannot_claim_replication_early():
    records = _records(6)
    prediction = cycle._build_prediction(6, "snapshot-hash", records[:5], "2026-09-13T12:00:00+00:00")
    cycle._evaluate_prediction(prediction, records[5])
    ledger = cycle._empty_ledger()
    ledger["predictions"] = [prediction]
    summary = cycle.summarize_ledger(ledger)
    assert summary["evaluated_predictions"] == 1
    assert summary["prospective_state"] == "UNDER_TEST_COHORT_A"
    assert summary["predictive_evidence"] == "NOT_ESTABLISHED"
    assert summary["replication_criteria_met"] is False


def test_protocol_is_frozen_by_hash(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = cycle._empty_ledger()
    path.write_text(__import__("json").dumps(ledger), encoding="utf-8")
    loaded = cycle._load_ledger(path)
    assert loaded["protocol"]["protocol_hash"] == cycle._protocol()["protocol_hash"]
    ledger["protocol"]["delta_min"] = 0.0
    path.write_text(__import__("json").dumps(ledger), encoding="utf-8")
    with pytest.raises(RuntimeError, match="protocol changed"):
        cycle._load_ledger(path)
