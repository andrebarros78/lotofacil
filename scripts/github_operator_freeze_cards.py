from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.portfolios.frozen import (
    empty_operator_card_ledger,
    freeze_operator_cards,
    validate_operator_card_ledger,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _reserved_primary_cards(prospective_ledger: dict, target_contest: int) -> list[list[int]]:
    reserved: list[list[int]] = []
    for prediction in prospective_ledger.get("predictions", []):
        if int(prediction.get("target_contest", -1)) != target_contest:
            continue
        primary = prediction.get("primary_card")
        if isinstance(primary, dict) and isinstance(primary.get("card"), list):
            reserved.append(primary["card"])
    return reserved


def run(
    state_dir: Path,
    *,
    card_count: int,
    idempotency_key: str,
    source_commit: str,
    workflow_run_id: str,
    target_contest: int = 0,
) -> dict[str, object]:
    latest = _load(state_dir / "latest.json")
    prospective = _load(state_dir / "prospective_ledger.json")
    canonical_target = int(latest["next_prediction_target"])
    official_latest = int(latest["official_latest_contest"])
    target = canonical_target if target_contest == 0 else int(target_contest)
    if target <= official_latest:
        raise RuntimeError(
            f"OPERATOR_CARD_TARGET_ALREADY_OBSERVED: requested={target} official_latest={official_latest}"
        )
    if target != canonical_target:
        raise RuntimeError(
            f"OPERATOR_CARD_TARGET_MUST_EQUAL_CANONICAL_NEXT: requested={target} canonical={canonical_target}"
        )

    prediction = next(
        (item for item in prospective.get("predictions", []) if int(item.get("target_contest", -1)) == target),
        None,
    )
    if prediction is None:
        raise RuntimeError("OPERATOR_CARD_TARGET_HAS_NO_FROZEN_PREDICTION")
    if int(prediction.get("training_last_contest", -1)) != official_latest:
        raise RuntimeError("OPERATOR_CARD_PREDICTION_TRAINING_CUTOFF_MISMATCH")
    if not isinstance(prediction.get("primary_card"), dict):
        raise RuntimeError("OPERATOR_CARD_PRIMARY_CARD_NOT_FROZEN")

    ledger_path = state_dir / "operator_card_ledger.json"
    ledger = _load(ledger_path) if ledger_path.exists() else empty_operator_card_ledger()
    validate_operator_card_ledger(ledger)
    reserved = _reserved_primary_cards(prospective, target)
    ledger, result = freeze_operator_cards(
        ledger,
        target_contest=target,
        requested_card_count=card_count,
        state_snapshot_hash=str(latest["snapshot_hash"]),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        idempotency_key=idempotency_key,
        source_commit=source_commit,
        workflow_run_id=workflow_run_id,
        reserved_cards=reserved,
    )
    _write(ledger_path, ledger)
    return {
        **result,
        "official_latest_contest": official_latest,
        "canonical_next_prediction_target": canonical_target,
        "state_snapshot_id": latest["snapshot_id"],
        "state_snapshot_hash": latest["snapshot_hash"],
        "predictive_evidence": latest["prospective"]["predictive_evidence"],
        "operator_card_ledger": "operations/operator_card_ledger.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and freeze additive operator cards in GitHub state")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--card-count", type=int, required=True)
    parser.add_argument("--target-contest", type=int, default=0)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.state_dir,
        card_count=args.card_count,
        target_contest=args.target_contest,
        idempotency_key=args.idempotency_key,
        source_commit=args.source_commit,
        workflow_run_id=args.workflow_run_id,
    )
    _write(args.out, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
