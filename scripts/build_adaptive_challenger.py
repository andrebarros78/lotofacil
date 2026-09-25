from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.portfolios.adaptive import build_adaptive_primary_card


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_adaptive_challenger(state_dir: Path) -> dict[str, object]:
    history_path = state_dir / "canonical_history.json"
    ledger_path = state_dir / "prospective_ledger.json"
    latest_path = state_dir / "latest.json"
    history = _load(history_path)
    ledger = _load(ledger_path)
    latest = _load(latest_path)

    records = history.get("records", [])
    if not records:
        raise RuntimeError("ADAPTIVE_CANONICAL_HISTORY_EMPTY")
    training_last = int(records[-1]["contest_id"])
    target = int(latest["next_prediction_target"])
    if target != training_last + 1:
        raise RuntimeError("ADAPTIVE_STATE_TARGET_MISMATCH")
    draws = tuple(tuple(int(number) for number in record["numbers"]) for record in records)

    decision = build_adaptive_primary_card(
        draws,
        target_contest=target,
        training_last_contest=training_last,
    )
    pending = next(
        (
            item
            for item in ledger.get("predictions", [])
            if int(item.get("target_contest", -1)) == target
        ),
        None,
    )
    champion_card: list[int] | None = None
    champion_decision_sha256: str | None = None
    if isinstance(pending, dict):
        primary = pending.get("primary_card")
        if isinstance(primary, dict) and isinstance(primary.get("card"), list):
            champion_card = [int(number) for number in primary["card"]]
            champion_decision_sha256 = str(primary.get("decision_sha256"))

    overlap = None
    changed_positions = None
    if champion_card is not None:
        overlap = len(set(champion_card).intersection(decision.card))
        changed_positions = 15 - overlap

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "ADAPTIVE_CHALLENGER_FROZEN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "training_last_contest": training_last,
        "predictive_evidence": "NOT_ESTABLISHED",
        "operational_use_allowed": True,
        "evidence_label": decision.evidence_label,
        "selection_method": decision.selection_method,
        "decision_sha256": decision.decision_sha256,
        "selected_model": decision.to_dict()["selected_model"],
        "selected_metrics": decision.to_dict()["selected_metrics"],
        "validation_windows": decision.validation_windows,
        "card": list(decision.card),
        "card_display": " ".join(f"{number:02d}" for number in decision.card),
        "ranking": list(decision.ranking),
        "probabilities": list(decision.probabilities),
        "leaderboard": decision.to_dict()["leaderboard"],
        "champion_control": {
            "card": champion_card,
            "decision_sha256": champion_decision_sha256,
            "overlap": overlap,
            "changed_positions": changed_positions,
        },
        "provenance": {
            "canonical_history_sha256": _sha256(history_path),
            "prospective_ledger_sha256": _sha256(ledger_path),
            "latest_sha256": _sha256(latest_path),
        },
        "policy": {
            "role": "PROSPECTIVE_CHALLENGER",
            "future_results_forbidden": True,
            "retroactive_rewrite_forbidden": True,
            "champion_control_preserved": True,
            "selection_objective": "mean_hits_top15_then_tail12_tail11_then_brier",
        },
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_adaptive_challenger(args.state_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "target_contest": payload["target_contest"],
                "selected_model": payload["selected_model"],
                "card": payload["card"],
                "changed_positions": payload["champion_control"]["changed_positions"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
