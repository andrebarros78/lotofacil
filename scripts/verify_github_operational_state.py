from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_reports,
    render_post_contest_report_markdown,
)
from sare_lotofacil.evaluation import CANONICAL_EVALUATION
from sare_lotofacil.experiments.models import exponential_update, frequency_regularized
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.operational_state import verify_state_commit
from sare_lotofacil.portfolios.authority import (
    POLICY_PRIMARY,
    STATUS_FROZEN,
    validate_card_artifact,
)
from sare_lotofacil.portfolios.frozen import (
    card_for_generation_index,
    validate_operator_card_ledger,
)
from sare_lotofacil.portfolios.primary import validate_primary_card_payload
from sare_lotofacil.persistence.snapshot_identity import semantic_data_snapshot_hash
from sare_lotofacil.statistics.baseline import brier_score, uniform_baseline

PRIMARY_MODEL = "M1_frequency_regularized_lambda_100"
SECONDARY_MODEL = "M2_exponential_alpha_0.05"


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _prediction_hash_payload(prediction: dict[str, object]) -> dict[str, object]:
    payload = {
        "target_contest": prediction["target_contest"],
        "created_at_utc": prediction["created_at_utc"],
        "training_last_contest": prediction["training_last_contest"],
        "training_snapshot_hash": prediction["training_snapshot_hash"],
        "protocol_hash": prediction["protocol_hash"],
        "models": prediction["models"],
    }
    if "training_data_snapshot_hash" in prediction:
        payload["training_data_snapshot_hash"] = prediction["training_data_snapshot_hash"]
    if "primary_card" in prediction:
        payload["primary_card"] = prediction["primary_card"]
    if "primary_card_artifact" in prediction:
        payload["primary_card_artifact"] = prediction["primary_card_artifact"]
    return payload


def _verify_operator_cards(state_dir: Path, prospective: dict[str, object]) -> dict[str, object]:
    path = state_dir / "operator_card_ledger.json"
    if not path.exists():
        return {
            "status": "OPERATOR_CARD_LEDGER_NOT_INITIALIZED",
            "requests": 0,
            "operator_frozen_cards": 0,
            "targets": 0,
        }
    operator_ledger = json.loads(path.read_text(encoding="utf-8"))
    result = validate_operator_card_ledger(operator_ledger)

    predictions_by_target: dict[int, dict[str, object]] = {}
    reserved_by_target: dict[int, set[tuple[int, ...]]] = {}
    for prediction in prospective.get("predictions", []):
        target = int(prediction["target_contest"])
        predictions_by_target[target] = prediction
        primary = prediction.get("primary_card")
        if not isinstance(primary, dict) or not isinstance(primary.get("card"), list):
            continue
        reserved_by_target.setdefault(target, set()).add(tuple(int(number) for number in primary["card"]))

    occupied_by_target = {target: set(cards) for target, cards in reserved_by_target.items()}
    cursor_by_target: dict[int, int] = {}
    for request in operator_ledger.get("requests", []):
        target = int(request["target_contest"])
        prediction = predictions_by_target.get(target)
        if prediction is None:
            raise RuntimeError("OPERATOR_CARD_TARGET_HAS_NO_FROZEN_PREDICTION")
        latest = json.loads((state_dir / "latest.json").read_text(encoding="utf-8"))
        if target == int(latest["next_prediction_target"]):
            request_data_hash = request.get("state_data_snapshot_hash")
            if request_data_hash is not None:
                latest_data_hash = latest.get("data_snapshot_hash")
                if latest_data_hash is None or str(request_data_hash) != str(latest_data_hash):
                    raise RuntimeError("OPERATOR_CARD_STATE_DATA_SNAPSHOT_MISMATCH")
            elif str(request["state_snapshot_hash"]) != str(latest["snapshot_hash"]):
                raise RuntimeError("OPERATOR_CARD_STATE_SNAPSHOT_MISMATCH")

        expected_start = cursor_by_target.get(target, 0)
        if int(request["generation_index_start"]) != expected_start:
            raise RuntimeError("OPERATOR_CARD_GENERATION_CURSOR_MISMATCH")
        occupied = occupied_by_target.setdefault(target, set())
        cursor = expected_start

        for item in request.get("cards", []):
            index = int(item["generation_index"])
            while cursor < index:
                skipped = card_for_generation_index(target, cursor)
                if skipped not in occupied:
                    raise RuntimeError("OPERATOR_CARD_UNJUSTIFIED_GENERATION_SKIP")
                cursor += 1

            card = tuple(int(number) for number in item["card"])
            expected_card = card_for_generation_index(target, index)
            if card != expected_card:
                raise RuntimeError("OPERATOR_CARD_GENERATION_PROOF_MISMATCH")
            if card in occupied:
                raise RuntimeError("OPERATOR_CARD_SELECTED_OCCUPIED_COMBINATION")
            occupied.add(card)
            cursor = index + 1

        if int(request["generation_index_next"]) != cursor:
            raise RuntimeError("OPERATOR_CARD_UNJUSTIFIED_TRAILING_SKIP")
        cursor_by_target[target] = cursor

    return result

def verify(state_dir: Path) -> dict[str, object]:
    state_commit = verify_state_commit(state_dir, allow_legacy=True)
    canonical_path = state_dir / "canonical_history.json"
    ledger_path = state_dir / "prospective_ledger.json"
    latest_path = state_dir / "latest.json"
    manifest_path = state_dir / "bootstrap_manifest.json"
    for path in (canonical_path, ledger_path, latest_path, manifest_path):
        if not path.exists():
            raise RuntimeError(f"missing operational state file: {path.name}")

    history = json.loads(canonical_path.read_text(encoding="utf-8"))
    records = tuple(
        validate_contest(int(item["contest_id"]), date.fromisoformat(item["draw_date"]), item["numbers"])
        for item in history["records"]
    )
    expected_ids = list(range(1, records[-1].contest_id + 1))
    if [record.contest_id for record in records] != expected_ids:
        raise RuntimeError("canonical history is not contiguous")
    by_id = {record.contest_id: record for record in records}

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    protocol = ledger["protocol"]
    protocol_without_hash = {key: value for key, value in protocol.items() if key != "protocol_hash"}
    if protocol.get("protocol_hash") != _sha256(protocol_without_hash):
        raise RuntimeError("protocol hash mismatch")

    evaluated = 0
    pending = 0
    pending_targets: list[int] = []
    predictions_by_target: dict[int, dict[str, object]] = {}
    for prediction in ledger.get("predictions", []):
        target = int(prediction["target_contest"])
        training_last = int(prediction["training_last_contest"])
        if target in predictions_by_target:
            raise RuntimeError(f"duplicate prediction target: {target}")
        predictions_by_target[target] = prediction
        if target != training_last + 1:
            raise RuntimeError("prediction target is not adjacent to training cutoff")
        if prediction.get("prediction_sha256") != _sha256(_prediction_hash_payload(prediction)):
            raise RuntimeError(f"prediction hash mismatch: {target}")

        models = prediction.get("models")
        if not isinstance(models, dict):
            raise RuntimeError(f"prediction models missing: {target}")
        training_records = tuple(record for record in records if record.contest_id <= training_last)
        if len(training_records) != training_last:
            raise RuntimeError(f"training history is incomplete for prediction: {target}")
        training_draws = tuple(record.numbers for record in training_records)
        expected_training_data_hash = semantic_data_snapshot_hash(training_records)
        stored_training_data_hash = prediction.get("training_data_snapshot_hash")
        if (
            stored_training_data_hash is not None
            and str(stored_training_data_hash) != expected_training_data_hash
        ):
            raise RuntimeError(f"prediction semantic snapshot mismatch: {target}")
        expected_models = {
            "M0_uniform": tuple(uniform_baseline()),
            PRIMARY_MODEL: tuple(frequency_regularized(training_draws, lam=100.0)),
        }
        m2 = uniform_baseline()
        for draw in training_draws:
            m2 = exponential_update(m2, draw, alpha=0.05)
        expected_models[SECONDARY_MODEL] = tuple(m2)
        for model_name, expected_scores in expected_models.items():
            observed_scores = models.get(model_name)
            if not isinstance(observed_scores, list) or len(observed_scores) != 25:
                raise RuntimeError(f"prediction model payload invalid: {target} {model_name}")
            if any(abs(float(observed) - float(expected)) > 1e-12 for observed, expected in zip(observed_scores, expected_scores)):
                raise RuntimeError(f"prediction model drift from canonical training data: {target} {model_name}")

        primary_card = prediction.get("primary_card")
        if primary_card is not None:
            try:
                decision = validate_primary_card_payload(
                    primary_card,
                    models[PRIMARY_MODEL],
                    models[SECONDARY_MODEL],
                    target_contest=target,
                    training_last_contest=training_last,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                raise RuntimeError(f"primary card semantic mismatch: {target}") from exc
            artifact_payload = prediction.get("primary_card_artifact")
            if artifact_payload is not None:
                artifact = validate_card_artifact(
                    artifact_payload,
                    expected_status=STATUS_FROZEN,
                    expected_cards=(decision.card,),
                    require_operational=True,
                )
                if artifact.policy_id != POLICY_PRIMARY:
                    raise RuntimeError(f"primary card artifact policy mismatch: {target}")
                if artifact.target_contest != target or artifact.training_last_contest != training_last:
                    raise RuntimeError(f"primary card artifact target mismatch: {target}")
                if artifact.storage_snapshot_hash != str(prediction["training_snapshot_hash"]):
                    raise RuntimeError(f"primary card artifact storage snapshot mismatch: {target}")
                if stored_training_data_hash is not None and artifact.data_snapshot_hash != expected_training_data_hash:
                    raise RuntimeError(f"primary card artifact semantic snapshot mismatch: {target}")
                if artifact.metadata.get("decision_sha256") != decision.decision_sha256:
                    raise RuntimeError(f"primary card artifact decision mismatch: {target}")

        evaluation = prediction.get("evaluation")
        if evaluation is None:
            pending += 1
            pending_targets.append(target)
            if target <= records[-1].contest_id:
                raise RuntimeError(f"unevaluated prediction already has official history: {target}")
            continue

        evaluated += 1
        record = by_id.get(target)
        if record is None:
            raise RuntimeError(f"evaluation has no canonical result: {target}")
        if int(evaluation.get("observed_contest", 0)) != target:
            raise RuntimeError(f"evaluation contest mismatch: {target}")
        if str(evaluation.get("observed_draw_date", "")) != record.draw_date.isoformat():
            raise RuntimeError(f"evaluation draw date mismatch: {target}")
        observed_numbers = evaluation.get("observed_numbers")
        if not isinstance(observed_numbers, list) or tuple(int(number) for number in observed_numbers) != record.numbers:
            raise RuntimeError(f"evaluation observed numbers mismatch: {target}")

        recomputed = {
            "M0_uniform": brier_score(models["M0_uniform"], record.numbers),
            PRIMARY_MODEL: brier_score(models[PRIMARY_MODEL], record.numbers),
            SECONDARY_MODEL: brier_score(models[SECONDARY_MODEL], record.numbers),
        }
        stored = evaluation["scores"]
        for model, score in recomputed.items():
            if abs(float(stored[model]) - score) > 1e-12:
                raise RuntimeError(f"score mismatch for contest {target} model {model}")
        if abs(float(evaluation["delta_brier"][PRIMARY_MODEL]) - (recomputed["M0_uniform"] - recomputed[PRIMARY_MODEL])) > 1e-12:
            raise RuntimeError(f"primary delta mismatch for contest {target}")
        if abs(float(evaluation["delta_brier"][SECONDARY_MODEL]) - (recomputed["M0_uniform"] - recomputed[SECONDARY_MODEL])) > 1e-12:
            raise RuntimeError(f"secondary delta mismatch for contest {target}")

        card_evaluation = prediction.get("primary_card_evaluation")
        if primary_card is not None:
            if not isinstance(card_evaluation, dict):
                raise RuntimeError(f"primary card evaluation missing: {target}")
            if int(card_evaluation.get("observed_contest", 0)) != target:
                raise RuntimeError(f"primary card evaluation contest mismatch: {target}")
            expected_hits = len(set(int(number) for number in primary_card["card"]) & set(record.numbers))
            if int(card_evaluation.get("hits", -1)) != expected_hits:
                raise RuntimeError(f"primary card hit mismatch: {target}")
        elif card_evaluation is not None:
            raise RuntimeError(f"primary card evaluation without frozen card: {target}")

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    actual_history_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    actual_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    actual_data_snapshot_hash = semantic_data_snapshot_hash(records)
    expected_next_target = records[-1].contest_id + 1
    if int(latest["official_latest_contest"]) != records[-1].contest_id:
        raise RuntimeError("latest report diverges from canonical history")
    if int(latest["next_prediction_target"]) != expected_next_target:
        raise RuntimeError("latest next prediction target diverges from canonical history")
    if int(latest["snapshot_contests"]) != len(records):
        raise RuntimeError("latest snapshot contest count diverges from canonical history")
    if str(latest["canonical_history_sha256"]) != actual_history_sha256:
        raise RuntimeError("latest canonical history hash diverges from persisted bytes")
    if (
        latest.get("data_snapshot_hash") is not None
        and str(latest["data_snapshot_hash"]) != actual_data_snapshot_hash
    ):
        raise RuntimeError("latest semantic data snapshot hash diverges from canonical history")
    if latest.get("storage_snapshot_id") is not None and str(latest["storage_snapshot_id"]) != str(latest["snapshot_id"]):
        raise RuntimeError("latest storage snapshot id alias mismatch")
    if latest.get("storage_snapshot_hash") is not None and str(latest["storage_snapshot_hash"]) != str(latest["snapshot_hash"]):
        raise RuntimeError("latest storage snapshot hash alias mismatch")
    if str(latest["bootstrap_manifest_sha256"]) != actual_manifest_sha256:
        raise RuntimeError("latest bootstrap manifest hash diverges from persisted bytes")
    if pending_targets != [expected_next_target]:
        raise RuntimeError(
            f"pending prediction set mismatch: expected={[expected_next_target]} observed={pending_targets}"
        )
    if latest["prospective"] != ledger["summary"]:
        raise RuntimeError("latest prospective summary diverges from ledger")
    if state_commit["status"] == "STATE_COMMIT_VERIFIED":
        transaction = latest.get("state_transaction")
        if not isinstance(transaction, dict):
            raise RuntimeError("latest state transaction metadata missing")
        commit_metadata = state_commit.get("metadata")
        if not isinstance(commit_metadata, dict):
            raise RuntimeError("state commit metadata missing")
        cycle_generation = commit_metadata.get("cycle_generation_id")
        if transaction.get("generation_id") != cycle_generation:
            raise RuntimeError("latest cycle generation diverges from state commit ancestry")

    expected_reports = build_post_contest_reports(ledger)
    report_summary = latest.get("post_contest_report")
    if report_summary is None:
        post_contest_reports = {"status": "POST_CONTEST_REPORT_STATE_NOT_INITIALIZED"}
    else:
        reports_path = state_dir / "post_contest_reports.json"
        latest_report_path = state_dir / "latest_post_contest_report.json"
        latest_report_md_path = state_dir / "latest_post_contest_report.md"
        for path in (reports_path, latest_report_path, latest_report_md_path):
            if not path.exists():
                raise RuntimeError(f"missing post-contest report state file: {path.name}")
        stored_reports = json.loads(reports_path.read_text(encoding="utf-8"))
        stored_latest = json.loads(latest_report_path.read_text(encoding="utf-8"))
        if stored_reports != expected_reports:
            raise RuntimeError("post-contest report ledger diverges from prospective ledger")
        if stored_latest != expected_reports["latest_report"]:
            raise RuntimeError("latest post-contest report diverges from report ledger")
        expected_markdown = render_post_contest_report_markdown(stored_latest) + "\n"
        if latest_report_md_path.read_text(encoding="utf-8") != expected_markdown:
            raise RuntimeError("latest post-contest markdown diverges from canonical report")
        if int(report_summary["report_count"]) != int(expected_reports["report_count"]):
            raise RuntimeError("latest post-contest report count mismatch")
        if report_summary["latest_contest"] != expected_reports["latest_contest"]:
            raise RuntimeError("latest post-contest contest mismatch")
        post_contest_reports = {
            "status": "POST_CONTEST_REPORT_STATE_PASS",
            "report_count": expected_reports["report_count"],
            "latest_contest": expected_reports["latest_contest"],
        }

    operator_cards = _verify_operator_cards(state_dir, ledger)
    return {
        "status": "GITHUB_OPERATIONAL_AUDIT_PASS",
        "canonical_contests": len(records),
        "last_contest": records[-1].contest_id,
        "evaluated_predictions": evaluated,
        "pending_predictions": pending,
        "evaluation_isolation": {
            "evaluation_class": CANONICAL_EVALUATION,
            "canonical_binding_verified": True,
            "canonical_source": "canonical_history.json",
            "evaluated_predictions_verified": evaluated,
        },
        "protocol_hash": protocol["protocol_hash"],
        "canonical_history_sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
        "data_snapshot_hash": actual_data_snapshot_hash,
        "data_snapshot_state": (
            "PERSISTED_MATCH"
            if latest.get("data_snapshot_hash") is not None
            else "LEGACY_COMPUTED"
        ),
        "storage_snapshot_id": latest.get("storage_snapshot_id", latest.get("snapshot_id")),
        "storage_snapshot_hash": latest.get("storage_snapshot_hash", latest.get("snapshot_hash")),
        "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "predictive_evidence": ledger["summary"].get("predictive_evidence", "NOT_ESTABLISHED"),
        "prospective_state": ledger["summary"].get("prospective_state"),
        "operator_cards": operator_cards,
        "post_contest_reports": post_contest_reports,
        "state_transaction": state_commit,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/github_operational_audit.json")
    args = parser.parse_args()
    result = verify(Path(args.state_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
