from datetime import date, timedelta
from types import SimpleNamespace
from urllib.error import HTTPError

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


def test_prediction_evaluation_rejects_wrong_contest_record():
    records = _records(7)
    prediction = cycle._build_prediction(6, "snapshot-hash", records[:5], "2026-09-13T12:00:00+00:00")
    with pytest.raises(RuntimeError, match="PREDICTION_EVALUATION_TARGET_MISMATCH"):
        cycle._evaluate_prediction(prediction, records[6])


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


def _contest_ref(contest_id: int):
    return SimpleNamespace(record=SimpleNamespace(contest_id=contest_id))


def test_resolve_official_latest_probes_next_when_latest_endpoint_lags(monkeypatch):
    calls = []

    def fake_fetch(contest_id=None):
        calls.append(contest_id)
        if contest_id is None:
            return _contest_ref(3783)
        assert contest_id == 3784
        return _contest_ref(3784)

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    resolved = cycle._resolve_official_latest(3783)

    assert resolved.record.contest_id == 3784
    assert calls == [None, 3784]


def test_resolve_official_latest_keeps_current_when_next_is_not_published(monkeypatch):
    def fake_fetch(contest_id=None):
        if contest_id is None:
            return _contest_ref(3783)
        raise HTTPError(
            url=f"https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/{contest_id}",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    resolved = cycle._resolve_official_latest(3783)

    assert resolved.record.contest_id == 3783


def test_resolve_official_latest_fails_closed_on_unexpected_probe_result(monkeypatch):
    def fake_fetch(contest_id=None):
        if contest_id is None:
            return _contest_ref(3783)
        return _contest_ref(3785)

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    with pytest.raises(RuntimeError, match="unexpected contest"):
        cycle._resolve_official_latest(3783)


def test_cycle_builds_constructive_post_contest_report_for_transactional_publish():
    records = _records(6)
    prediction = cycle._build_prediction(6, "snapshot-hash", records[:5], "2026-09-13T12:00:00+00:00")
    cycle._evaluate_prediction(prediction, records[5])
    ledger = cycle._empty_ledger()
    ledger["predictions"] = [prediction]
    ledger["summary"] = cycle.summarize_ledger(ledger)

    report_state, report_files = cycle._build_post_contest_report_files(ledger)

    assert report_state["report_count"] == 1
    assert report_state["latest_contest"] == 6
    assert "post_contest_reports.json" in report_files
    assert "latest_post_contest_report.json" in report_files
    markdown = report_files["latest_post_contest_report.md"].decode("utf-8")
    assert "Concurso Número: 6" in markdown
    assert "Resultado:" in markdown
    assert "Cartão gerado:" in markdown
    assert "Número de acertos:" in markdown
    assert "Autoanálise do processo" in markdown


def test_resolve_official_latest_recovers_when_latest_endpoint_is_behind_state(monkeypatch):
    calls = []

    def fake_fetch(contest_id=None):
        calls.append(contest_id)
        if contest_id is None:
            return _contest_ref(3783)
        if contest_id == 3784:
            return _contest_ref(3784)
        if contest_id == 3785:
            raise HTTPError(
                url="https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/3785",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            )
        raise AssertionError(contest_id)

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    resolved = cycle._resolve_official_latest(3784)

    assert resolved.record.contest_id == 3784
    assert calls == [None, 3784, 3785]


def test_resolve_official_latest_still_fails_closed_when_state_cannot_be_verified(monkeypatch):
    def fake_fetch(contest_id=None):
        if contest_id is None:
            return _contest_ref(3783)
        raise HTTPError(
            url=f"https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/{contest_id}",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    with pytest.raises(RuntimeError, match="behind operational state"):
        cycle._resolve_official_latest(3784)


def test_resolve_official_latest_preserves_verified_current_on_next_probe_500(monkeypatch):
    calls = []

    def fake_fetch(contest_id=None):
        calls.append(contest_id)
        if contest_id is None:
            return _contest_ref(3783)
        if contest_id == 3784:
            return _contest_ref(3784)
        if contest_id == 3785:
            raise HTTPError(
                url="https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/3785",
                code=500,
                msg="Internal Server Error",
                hdrs=None,
                fp=None,
            )
        raise AssertionError(contest_id)

    monkeypatch.setattr(cycle, "fetch_caixa_contest", fake_fetch)

    resolved = cycle._resolve_official_latest(3784)

    assert resolved.record.contest_id == 3784
    assert calls == [None, 3784, 3785]
