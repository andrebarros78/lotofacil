from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.statistics.baseline import brier_score

PRIMARY_MODEL = "M1_frequency_regularized_lambda_100"
SECONDARY_MODEL = "M2_exponential_alpha_0.05"


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _prediction_hash_payload(prediction: dict[str, object]) -> dict[str, object]:
    return {
        "target_contest": prediction["target_contest"],
        "created_at_utc": prediction["created_at_utc"],
        "training_last_contest": prediction["training_last_contest"],
        "training_snapshot_hash": prediction["training_snapshot_hash"],
        "protocol_hash": prediction["protocol_hash"],
        "models": prediction["models"],
    }


def verify(state_dir: Path) -> dict[str, object]:
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
    for prediction in ledger.get("predictions", []):
        if int(prediction["training_last_contest"]) >= int(prediction["target_contest"]):
            raise RuntimeError("prediction contains future leakage")
        if prediction.get("prediction_sha256") != _sha256(_prediction_hash_payload(prediction)):
            raise RuntimeError(f"prediction hash mismatch: {prediction['target_contest']}")
        target = int(prediction["target_contest"])
        evaluation = prediction.get("evaluation")
        if evaluation is None:
            pending += 1
            if target <= records[-1].contest_id:
                raise RuntimeError(f"unevaluated prediction already has official history: {target}")
            continue
        evaluated += 1
        record = by_id.get(target)
        if record is None:
            raise RuntimeError(f"evaluation has no canonical result: {target}")
        models = prediction["models"]
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

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    if int(latest["official_latest_contest"]) != records[-1].contest_id:
        raise RuntimeError("latest report diverges from canonical history")
    if latest["prospective"] != ledger["summary"]:
        raise RuntimeError("latest prospective summary diverges from ledger")

    return {
        "status": "GITHUB_OPERATIONAL_AUDIT_PASS",
        "canonical_contests": len(records),
        "last_contest": records[-1].contest_id,
        "evaluated_predictions": evaluated,
        "pending_predictions": pending,
        "protocol_hash": protocol["protocol_hash"],
        "canonical_history_sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
        "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "predictive_evidence": ledger["summary"].get("predictive_evidence", "NOT_ESTABLISHED"),
        "prospective_state": ledger["summary"].get("prospective_state"),
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
