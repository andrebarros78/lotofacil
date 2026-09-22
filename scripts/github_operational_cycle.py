from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import stdev
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_reports,
    render_post_contest_report_markdown,
)
from sare_lotofacil.experiments.models import exponential_update, frequency_regularized
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.ingestion.csv_history import parse_history_csv
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.operational_state import (
    publish_state_transaction,
    recover_state_transaction,
    verify_state_commit,
)
from sare_lotofacil.persistence.backup import database_integrity
from sare_lotofacil.persistence.repository import (
    create_latest_snapshot,
    load_snapshot_records,
    persist_caixa_contest,
    persist_history_records,
)
from sare_lotofacil.portfolios.authority import CardGenerationService
from sare_lotofacil.portfolios.primary import (
    PRIMARY_MODEL_NAME,
    SECONDARY_MODEL_NAME,
    select_primary_card,
)
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER, brier_score, uniform_baseline

SOURCE_URL = "https://raw.githubusercontent.com/heldersontuc-collab/lotofacil-data/main/data/lotofacil.csv"
PROTOCOL_VERSION = "prospective-m1-v1"
PRIMARY_MODEL = PRIMARY_MODEL_NAME
SECONDARY_MODEL = SECONDARY_MODEL_NAME
DELTA_MIN = 0.0005
COHORT_SIZE = 100
MAX_BOOTSTRAP_PATCHES = 1000


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pretty_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _download(url: str) -> bytes:
    request = Request(url, headers={"Accept": "text/csv", "User-Agent": "SARE-Lotofacil/1.1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _resolve_official_latest(current_last: int):
    official_latest = fetch_caixa_contest()
    official_id = official_latest.record.contest_id

    if official_id > current_last:
        return official_latest

    if official_id < current_last:
        try:
            current_official = fetch_caixa_contest(current_last)
        except HTTPError as exc:
            if exc.code in {400, 404}:
                raise RuntimeError("official latest contest is behind operational state") from exc
            raise
        if current_official.record.contest_id != current_last:
            raise RuntimeError("official current-contest verification returned an unexpected contest")
        official_latest = current_official

    next_contest = current_last + 1
    try:
        candidate = fetch_caixa_contest(next_contest)
    except HTTPError as exc:
        if exc.code in {400, 404, 500}:
            return official_latest
        raise

    if candidate.record.contest_id != next_contest:
        raise RuntimeError("official next-contest probe returned an unexpected contest")
    return candidate


def _paired_interval(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, mean, mean
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def _m2_next(draws: tuple[tuple[int, ...], ...], alpha: float = 0.05) -> tuple[float, ...]:
    probabilities = uniform_baseline()
    for draw in draws:
        probabilities = exponential_update(probabilities, draw, alpha=alpha)
    return probabilities


def _protocol() -> dict[str, object]:
    protocol = {
        "protocol_version": PROTOCOL_VERSION,
        "primary_model": PRIMARY_MODEL,
        "secondary_model": SECONDARY_MODEL,
        "primary_metric": "paired_delta_brier_vs_M0",
        "uniform_brier": UNIFORM_BRIER,
        "delta_min": DELTA_MIN,
        "cohort_size": COHORT_SIZE,
        "replication_rule": (
            "PRIMARY model must independently satisfy mean_delta > delta_min and 95% CI low > delta_min "
            "in cohort A contests 1-100 and cohort B contests 101-200. No model promotion occurs automatically."
        ),
        "prediction_rule": "prediction for contest N is frozen using only contests <= N-1",
        "tamper_rule": "prediction payload SHA-256 must verify before any evaluation",
    }
    protocol["protocol_hash"] = _sha256(protocol)
    return protocol


def _empty_ledger() -> dict[str, object]:
    return {
        "schema_version": 1,
        "protocol": _protocol(),
        "predictions": [],
        "summary": {},
    }


def _load_ledger(path: Path) -> dict[str, object]:
    if not path.exists():
        return _empty_ledger()
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("protocol") != _protocol():
        raise RuntimeError("prospective protocol changed after initialization")
    verify_prediction_hashes(ledger)
    return ledger


def _prediction_hash_payload(prediction: dict[str, object]) -> dict[str, object]:
    payload = {
        "target_contest": prediction["target_contest"],
        "created_at_utc": prediction["created_at_utc"],
        "training_last_contest": prediction["training_last_contest"],
        "training_snapshot_hash": prediction["training_snapshot_hash"],
        "protocol_hash": prediction["protocol_hash"],
        "models": prediction["models"],
    }
    # Compatibilidade criptográfica: previsões congeladas antes da 1.1.8 não
    # possuíam PRIMARY_CARD. Novas previsões passam a selá-lo no mesmo hash.
    if "training_data_snapshot_hash" in prediction:
        payload["training_data_snapshot_hash"] = prediction["training_data_snapshot_hash"]
    if "primary_card" in prediction:
        payload["primary_card"] = prediction["primary_card"]
    if "primary_card_artifact" in prediction:
        payload["primary_card_artifact"] = prediction["primary_card_artifact"]
    return payload


def verify_prediction_hashes(ledger: dict[str, object]) -> None:
    for prediction in ledger.get("predictions", []):
        expected = prediction.get("prediction_sha256")
        observed = _sha256(_prediction_hash_payload(prediction))
        if expected != observed:
            raise RuntimeError(f"prediction hash mismatch for contest {prediction.get('target_contest')}")


def _build_prediction(
    target_contest: int,
    snapshot_hash: str,
    records,
    created_at_utc: str | None = None,
    *,
    data_snapshot_hash: str | None = None,
    storage_snapshot_id: str | None = None,
) -> dict[str, object]:
    draws = tuple(record.numbers for record in records)
    primary_scores = tuple(frequency_regularized(draws, lam=100.0))
    secondary_scores = tuple(_m2_next(draws, alpha=0.05))
    primary_card = select_primary_card(
        primary_scores,
        secondary_scores,
        target_contest=int(target_contest),
        training_last_contest=int(records[-1].contest_id),
    )
    primary_artifact = CardGenerationService.freeze_primary(
        card=primary_card.card,
        target_contest=int(target_contest),
        training_last_contest=int(records[-1].contest_id),
        decision_sha256=primary_card.decision_sha256,
        primary_model=primary_card.primary_model,
        secondary_model=primary_card.secondary_model,
        selection_method=primary_card.selection_method,
        data_snapshot_hash=data_snapshot_hash,
        storage_snapshot_id=storage_snapshot_id,
        storage_snapshot_hash=snapshot_hash,
    )
    prediction = {
        "target_contest": int(target_contest),
        "created_at_utc": created_at_utc or _utcnow(),
        "training_last_contest": int(records[-1].contest_id),
        "training_snapshot_hash": snapshot_hash,
        "protocol_hash": _protocol()["protocol_hash"],
        "models": {
            "M0_uniform": list(uniform_baseline()),
            PRIMARY_MODEL: list(primary_scores),
            SECONDARY_MODEL: list(secondary_scores),
        },
        "primary_card": primary_card.to_dict(),
        "primary_card_artifact": primary_artifact.to_dict(),
        "evaluation": None,
        "primary_card_evaluation": None,
    }
    if data_snapshot_hash is not None:
        prediction["training_data_snapshot_hash"] = data_snapshot_hash
    prediction["prediction_sha256"] = _sha256(_prediction_hash_payload(prediction))
    return prediction


def _evaluate_prediction(prediction: dict[str, object], observed_record) -> None:
    if prediction.get("evaluation") is not None:
        return
    verify_prediction_hashes({"predictions": [prediction]})
    target = int(prediction["target_contest"])
    training_last = int(prediction["training_last_contest"])
    if target != training_last + 1:
        raise RuntimeError("PREDICTION_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE")
    if int(observed_record.contest_id) != target:
        raise RuntimeError("PREDICTION_EVALUATION_TARGET_MISMATCH")
    models = prediction["models"]
    m0 = brier_score(models["M0_uniform"], observed_record.numbers)
    m1 = brier_score(models[PRIMARY_MODEL], observed_record.numbers)
    m2 = brier_score(models[SECONDARY_MODEL], observed_record.numbers)
    prediction["evaluation"] = {
        "evaluated_at_utc": _utcnow(),
        "observed_contest": observed_record.contest_id,
        "observed_draw_date": observed_record.draw_date.isoformat(),
        "observed_numbers": list(observed_record.numbers),
        "scores": {
            "M0_uniform": m0,
            PRIMARY_MODEL: m1,
            SECONDARY_MODEL: m2,
        },
        "delta_brier": {
            PRIMARY_MODEL: m0 - m1,
            SECONDARY_MODEL: m0 - m2,
        },
    }
    primary_card = prediction.get("primary_card")
    if isinstance(primary_card, dict) and isinstance(primary_card.get("card"), list):
        observed = set(observed_record.numbers)
        prediction["primary_card_evaluation"] = {
            "hits": sum(1 for number in primary_card["card"] if number in observed),
            "observed_contest": observed_record.contest_id,
        }


def _cohort_summary(evaluated: list[dict[str, object]], start: int, stop: int) -> dict[str, object]:
    cohort = evaluated[start:stop]
    primary = [item["evaluation"]["delta_brier"][PRIMARY_MODEL] for item in cohort]
    secondary = [item["evaluation"]["delta_brier"][SECONDARY_MODEL] for item in cohort]
    p_mean, p_low, p_high = _paired_interval(primary)
    s_mean, s_low, s_high = _paired_interval(secondary)
    return {
        "n": len(cohort),
        "primary_mean_delta": p_mean,
        "primary_ci95_low": p_low,
        "primary_ci95_high": p_high,
        "secondary_mean_delta": s_mean,
        "secondary_ci95_low": s_low,
        "secondary_ci95_high": s_high,
        "primary_gate_pass": bool(
            len(cohort) == COHORT_SIZE
            and p_mean is not None
            and p_low is not None
            and p_mean > DELTA_MIN
            and p_low > DELTA_MIN
        ),
    }


def summarize_ledger(ledger: dict[str, object]) -> dict[str, object]:
    evaluated = sorted(
        [item for item in ledger.get("predictions", []) if item.get("evaluation") is not None],
        key=lambda item: item["target_contest"],
    )
    all_primary = [item["evaluation"]["delta_brier"][PRIMARY_MODEL] for item in evaluated]
    mean, low, high = _paired_interval(all_primary)
    cohort_a = _cohort_summary(evaluated, 0, COHORT_SIZE)
    cohort_b = _cohort_summary(evaluated, COHORT_SIZE, COHORT_SIZE * 2)
    criteria_met = cohort_a["primary_gate_pass"] and cohort_b["primary_gate_pass"]
    if len(evaluated) < COHORT_SIZE:
        state = "UNDER_TEST_COHORT_A"
    elif not cohort_a["primary_gate_pass"]:
        state = "PRIMARY_NOT_REPLICATED_COHORT_A"
    elif len(evaluated) < COHORT_SIZE * 2:
        state = "UNDER_TEST_COHORT_B"
    elif criteria_met:
        state = "PROSPECTIVE_REPLICATION_CRITERIA_MET_REVIEW_REQUIRED"
    else:
        state = "PRIMARY_NOT_REPLICATED_COHORT_B"
    return {
        "evaluated_predictions": len(evaluated),
        "pending_predictions": sum(1 for item in ledger.get("predictions", []) if item.get("evaluation") is None),
        "primary_mean_delta": mean,
        "primary_ci95_low": low,
        "primary_ci95_high": high,
        "cohort_a": cohort_a,
        "cohort_b": cohort_b,
        "prospective_state": state,
        "replication_criteria_met": criteria_met,
        "predictive_evidence": "NOT_ESTABLISHED",
        "note": "Criteria met does not auto-promote: independent review remains required by project protocol.",
    }


def _serialize_records(records) -> list[dict[str, object]]:
    return [
        {
            "contest_id": record.contest_id,
            "draw_date": record.draw_date.isoformat(),
            "numbers": list(record.numbers),
        }
        for record in records
    ]


def _load_canonical_history(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = tuple(
        validate_contest(int(item["contest_id"]), date.fromisoformat(item["draw_date"]), item["numbers"])
        for item in payload["records"]
    )
    if not records or records[0].contest_id != 1:
        raise RuntimeError("canonical GitHub history must start at contest 1")
    expected = list(range(1, records[-1].contest_id + 1))
    observed = [record.contest_id for record in records]
    if observed != expected:
        raise RuntimeError("canonical GitHub history contains contest gaps or reordering")
    return records, payload


def _bootstrap_history(db_path: Path, canonical_path: Path, manifest_path: Path):
    raw = _download(SOURCE_URL)
    captured_at = datetime.now(timezone.utc)
    parsed = parse_history_csv(raw.decode("utf-8-sig"))
    non_gap = [issue for issue in parsed.issues if not issue.message.startswith("lacuna de concursos")]
    if non_gap:
        raise RuntimeError(f"invalid bootstrap source: {non_gap[0].message}")
    if not parsed.records or parsed.records[0].contest_id != 1:
        raise RuntimeError("bootstrap history must start at contest 1")
    bulk = persist_history_records(
        db_path,
        parsed.records,
        source_url=SOURCE_URL,
        raw_bytes=raw,
        captured_at=captured_at,
        source_class="TERCEIRO_CORROBORADO",
    )
    official_latest = fetch_caixa_contest()
    by_id = {record.contest_id for record in parsed.records}
    patch_ids = [contest_id for contest_id in range(1, official_latest.record.contest_id + 1) if contest_id not in by_id]
    if len(patch_ids) > MAX_BOOTSTRAP_PATCHES:
        raise RuntimeError(f"too many official bootstrap patches: {len(patch_ids)}")
    for contest_id in patch_ids:
        persist_caixa_contest(db_path, fetch_caixa_contest(contest_id), source_class="OFICIAL_DIRETA")
    snapshot = create_latest_snapshot(db_path)
    records = load_snapshot_records(db_path, snapshot.snapshot_id)
    canonical_payload = {
        "schema_version": 1,
        "created_at_utc": _utcnow(),
        "records": _serialize_records(records),
    }
    canonical_path.write_text(json.dumps(canonical_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "bootstrap_at_utc": _utcnow(),
        "source_url": SOURCE_URL,
        "source_sha256": bulk.source_sha256,
        "source_records": len(parsed.records),
        "official_latest_at_bootstrap": official_latest.record.contest_id,
        "official_patch_ids": patch_ids,
        "canonical_sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return records, patch_ids


def _prepare_database_from_state(state_dir: Path, runtime_dir: Path):
    state_canonical_path = state_dir / "canonical_history.json"
    state_manifest_path = state_dir / "bootstrap_manifest.json"
    canonical_path = runtime_dir / "canonical_history.next.json"
    manifest_path = runtime_dir / "bootstrap_manifest.next.json"
    db_path = runtime_dir / "sare.db"
    db_path.unlink(missing_ok=True)
    canonical_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)

    bootstrap_patches: list[int] = []
    if state_canonical_path.exists():
        canonical_path.write_bytes(state_canonical_path.read_bytes())
        if not state_manifest_path.exists():
            raise RuntimeError("bootstrap manifest missing from operational state")
        manifest_path.write_bytes(state_manifest_path.read_bytes())
        records, _ = _load_canonical_history(canonical_path)
        raw = canonical_path.read_bytes()
        persist_history_records(
            db_path,
            records,
            source_url="github://operations/state/operations/canonical_history.json",
            raw_bytes=raw,
            captured_at=datetime.now(timezone.utc),
            source_class="CANONICAL_GITHUB_STATE",
            media_type="application/json",
        )
    else:
        records, bootstrap_patches = _bootstrap_history(
            db_path,
            canonical_path,
            manifest_path,
        )
    return db_path, canonical_path, manifest_path, records, bootstrap_patches


def _build_post_contest_report_files(
    ledger: dict[str, object],
) -> tuple[dict[str, object], dict[str, bytes]]:
    report_state = build_post_contest_reports(ledger)
    files = {
        "post_contest_reports.json": _pretty_json_bytes(report_state),
    }
    latest_report = report_state["latest_report"]
    if latest_report is not None:
        files["latest_post_contest_report.json"] = _pretty_json_bytes(latest_report)
        files["latest_post_contest_report.md"] = (
            render_post_contest_report_markdown(latest_report) + "\n"
        ).encode("utf-8")
    return report_state, files


def run_cycle(state_dir: Path, runtime_dir: Path) -> dict[str, object]:
    state_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    recovery_outcome = recover_state_transaction(state_dir)
    commit_before = verify_state_commit(state_dir, allow_legacy=True)
    ledger_path = state_dir / "prospective_ledger.json"

    db_path, canonical_path, manifest_path, records, bootstrap_patches = _prepare_database_from_state(state_dir, runtime_dir)
    if database_integrity(db_path) != "ok":
        raise RuntimeError("operational database integrity check failed")

    snapshot = create_latest_snapshot(db_path)
    records = load_snapshot_records(db_path, snapshot.snapshot_id)
    current_last = records[-1].contest_id
    official_latest = _resolve_official_latest(current_last)
    inserted = []
    if official_latest.record.contest_id == current_last:
        persist_caixa_contest(db_path, official_latest, source_class="OFICIAL_DIRETA")
    else:
        for contest_id in range(current_last + 1, official_latest.record.contest_id + 1):
            persisted = persist_caixa_contest(db_path, fetch_caixa_contest(contest_id), source_class="OFICIAL_DIRETA")
            if persisted.created:
                inserted.append(contest_id)

    snapshot = create_latest_snapshot(db_path)
    records = load_snapshot_records(db_path, snapshot.snapshot_id)
    by_id = {record.contest_id: record for record in records}
    if records[-1].contest_id != official_latest.record.contest_id:
        raise RuntimeError("operational snapshot did not reach official latest contest")

    current_canonical_payload = json.loads(canonical_path.read_text(encoding="utf-8"))
    serialized_records = _serialize_records(records)
    if current_canonical_payload.get("records") != serialized_records:
        canonical_payload = {
            "schema_version": 1,
            "created_at_utc": current_canonical_payload.get("created_at_utc", _utcnow()),
            "updated_at_utc": _utcnow(),
            "records": serialized_records,
        }
        canonical_path.write_text(
            json.dumps(canonical_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    ledger = _load_ledger(ledger_path)
    evaluated_this_cycle: list[int] = []
    for prediction in ledger["predictions"]:
        target = int(prediction["target_contest"])
        if target in by_id and prediction.get("evaluation") is None:
            _evaluate_prediction(prediction, by_id[target])
            evaluated_this_cycle.append(target)

    next_target = records[-1].contest_id + 1
    if not any(int(item["target_contest"]) == next_target for item in ledger["predictions"]):
        ledger["predictions"].append(
            _build_prediction(
                next_target,
                snapshot.snapshot_hash,
                records,
                data_snapshot_hash=snapshot.data_snapshot_hash,
                storage_snapshot_id=snapshot.snapshot_id,
            )
        )
    verify_prediction_hashes(ledger)
    ledger["summary"] = summarize_ledger(ledger)

    report_state, report_files = _build_post_contest_report_files(ledger)

    core = analyze_core(tuple(record.numbers for record in records)).to_dict()
    result = {
        "status": "GITHUB_OPERATIONAL_CYCLE_PASS",
        "run_at_utc": _utcnow(),
        "database_integrity": database_integrity(db_path),
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "storage_snapshot_id": snapshot.storage_snapshot_id,
        "storage_snapshot_hash": snapshot.storage_snapshot_hash,
        "data_snapshot_hash": snapshot.data_snapshot_hash,
        "snapshot_contests": snapshot.contest_count,
        "official_latest_contest": official_latest.record.contest_id,
        "inserted_official_contests": inserted,
        "bootstrap_official_patches": bootstrap_patches,
        "canonical_history_sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
        "bootstrap_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "next_prediction_target": next_target,
        "prospective": ledger["summary"],
        "retrospective_core": core,
        "post_contest_report": {
            "report_count": report_state["report_count"],
            "latest_contest": report_state["latest_contest"],
            "emitted_for_contests": evaluated_this_cycle,
        },
    }
    generation_id = (
        f"cycle-{official_latest.record.contest_id}-"
        f"{_sha256({'canonical': result['canonical_history_sha256'], 'ledger': ledger['summary'], 'next': next_target})[:16]}"
    )
    result["state_transaction"] = {
        "schema": "operational-state-transaction-v1",
        "generation_id": generation_id,
        "recovery_before_cycle": recovery_outcome,
        "previous_commit_status": commit_before["status"],
    }
    state_files: dict[str, bytes] = {
        "bootstrap_manifest.json": manifest_path.read_bytes(),
        "canonical_history.json": canonical_path.read_bytes(),
        "prospective_ledger.json": _pretty_json_bytes(ledger),
        "latest.json": _pretty_json_bytes(result),
        **report_files,
    }
    with sqlite3.connect(db_path, timeout=30.0) as checkpoint_connection:
        checkpoint = checkpoint_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is None or int(checkpoint[0]) != 0:
            raise RuntimeError(f"operational database WAL checkpoint failed: {checkpoint}")
    runtime_db_sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
    previous_metadata = commit_before.get("metadata", {})
    previous_cycle_generation = (
        previous_metadata.get("cycle_generation_id")
        if isinstance(previous_metadata, dict)
        else None
    )
    if previous_cycle_generation == generation_id:
        verified_commit = verify_state_commit(state_dir, allow_legacy=False)
        result["state_transaction"]["commit_status"] = verified_commit["status"]
        result["state_transaction"]["committed_files"] = verified_commit["verified_files"]
        result["state_transaction"]["state_commit_generation_id"] = verified_commit["generation_id"]
        result["state_transaction"]["replay_noop"] = True
        return result

    commit = publish_state_transaction(
        state_dir,
        state_files,
        generation_id=generation_id,
        metadata={
            "source": "github_operational_cycle",
            "official_latest_contest": official_latest.record.contest_id,
            "next_prediction_target": next_target,
            "snapshot_id": snapshot.snapshot_id,
            "storage_snapshot_hash": snapshot.storage_snapshot_hash,
            "data_snapshot_hash": snapshot.data_snapshot_hash,
            "runtime_db_sha256": runtime_db_sha256,
            "database_integrity": result["database_integrity"],
        },
    )
    verified_commit = verify_state_commit(state_dir, allow_legacy=False)
    result["state_transaction"]["commit_status"] = verified_commit["status"]
    result["state_transaction"]["committed_files"] = verified_commit["verified_files"]
    result["state_transaction"]["state_commit_generation_id"] = commit["generation_id"]
    result["state_transaction"]["replay_noop"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--runtime-dir", default="artifacts/github-runtime")
    args = parser.parse_args()
    result = run_cycle(Path(args.state_dir), Path(args.runtime_dir))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
