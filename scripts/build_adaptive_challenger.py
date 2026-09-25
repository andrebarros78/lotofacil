from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from sare_lotofacil.portfolios.adaptive import build_adaptive_primary_card

UNIFORM_BRIER = 0.24


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_map(records: list[object]) -> dict[int, dict[str, object]]:
    mapped: dict[int, dict[str, object]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        contest_id = int(raw["contest_id"])
        mapped[contest_id] = raw
    return mapped


def _compact_entry(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "target_contest": int(payload["target_contest"]),
        "training_last_contest": int(payload["training_last_contest"]),
        "generated_at_utc": payload["generated_at_utc"],
        "selection_method": payload["selection_method"],
        "decision_sha256": payload["decision_sha256"],
        "selected_model": payload["selected_model"],
        "selected_metrics": payload["selected_metrics"],
        "validation_windows": payload["validation_windows"],
        "card": payload["card"],
        "probabilities": payload["probabilities"],
        "champion_control": payload["champion_control"],
        "predictive_evidence": payload.get("predictive_evidence", "NOT_ESTABLISHED"),
        "evaluation": None,
    }


def _evaluate_entry(entry: dict[str, object], official: Mapping[str, object]) -> dict[str, object]:
    if entry.get("evaluation") is not None:
        return entry
    observed = tuple(int(number) for number in official["numbers"])
    observed_set = set(observed)
    card = tuple(int(number) for number in entry["card"])
    card_set = set(card)
    probabilities = tuple(float(value) for value in entry["probabilities"])
    if len(probabilities) != 25:
        raise RuntimeError("ADAPTIVE_FROZEN_PROBABILITY_VECTOR_INVALID")
    brier = sum(
        (probability - (1.0 if number in observed_set else 0.0)) ** 2
        for number, probability in enumerate(probabilities, start=1)
    ) / 25.0

    champion = entry.get("champion_control")
    champion_hits = None
    if isinstance(champion, dict) and isinstance(champion.get("card"), list):
        champion_hits = len(set(int(number) for number in champion["card"]).intersection(observed_set))

    hits = len(card_set.intersection(observed_set))
    evaluated = dict(entry)
    evaluated["evaluation"] = {
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "observed_contest": int(official["contest_id"]),
        "observed_draw_date": official.get("draw_date"),
        "observed_numbers": list(observed),
        "hits": hits,
        "gap_to_15": 15 - hits,
        "selected_misses": sorted(card_set - observed_set),
        "omitted_winners": sorted(observed_set - card_set),
        "brier": brier,
        "delta_brier_vs_uniform": UNIFORM_BRIER - brier,
        "champion_hits": champion_hits,
        "delta_hits_vs_champion": None if champion_hits is None else hits - champion_hits,
    }
    return evaluated


def _history_from_existing(existing: dict[str, object] | None) -> list[dict[str, object]]:
    if existing is None:
        return []
    raw_history = existing.get("history")
    history: list[dict[str, object]] = []
    if isinstance(raw_history, list):
        for raw in raw_history:
            if isinstance(raw, dict):
                history.append(dict(raw))
    if isinstance(existing.get("target_contest"), int) and isinstance(existing.get("card"), list):
        target = int(existing["target_contest"])
        if not any(int(item.get("target_contest", -1)) == target for item in history):
            history.append(_compact_entry(existing))
    return history


def _history_summary(history: list[dict[str, object]]) -> dict[str, object]:
    evaluated = [item for item in history if isinstance(item.get("evaluation"), dict)]
    pending = [item for item in history if item.get("evaluation") is None]
    hits = [int(item["evaluation"]["hits"]) for item in evaluated]
    deltas = [
        int(item["evaluation"]["delta_hits_vs_champion"])
        for item in evaluated
        if item["evaluation"].get("delta_hits_vs_champion") is not None
    ]
    return {
        "entry_count": len(history),
        "evaluated_count": len(evaluated),
        "pending_count": len(pending),
        "best_hits": max(hits) if hits else None,
        "mean_hits": (sum(hits) / len(hits)) if hits else None,
        "wins_vs_champion": sum(delta > 0 for delta in deltas),
        "ties_vs_champion": sum(delta == 0 for delta in deltas),
        "losses_vs_champion": sum(delta < 0 for delta in deltas),
        "latest_target": max((int(item["target_contest"]) for item in history), default=None),
    }


def _build_new_current(
    *,
    records: list[object],
    ledger: dict[str, object],
    latest: dict[str, object],
    history_path: Path,
    ledger_path: Path,
    latest_path: Path,
) -> dict[str, object]:
    training_last = int(records[-1]["contest_id"])
    target = int(latest["next_prediction_target"])
    if target != training_last + 1:
        raise RuntimeError("ADAPTIVE_STATE_TARGET_MISMATCH")
    draws = tuple(tuple(int(number) for number in record["numbers"]) for record in records if isinstance(record, dict))

    decision = build_adaptive_primary_card(
        draws,
        target_contest=target,
        training_last_contest=training_last,
    )
    pending = next(
        (
            item
            for item in ledger.get("predictions", [])
            if isinstance(item, dict) and int(item.get("target_contest", -1)) == target
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

    decision_dict = decision.to_dict()
    return {
        "schema_version": 2,
        "status": "ADAPTIVE_CHALLENGER_FROZEN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "training_last_contest": training_last,
        "predictive_evidence": "NOT_ESTABLISHED",
        "operational_use_allowed": True,
        "evidence_label": decision.evidence_label,
        "selection_method": decision.selection_method,
        "decision_sha256": decision.decision_sha256,
        "selected_model": decision_dict["selected_model"],
        "selected_metrics": decision_dict["selected_metrics"],
        "validation_windows": decision.validation_windows,
        "card": list(decision.card),
        "card_display": " ".join(f"{number:02d}" for number in decision.card),
        "ranking": list(decision.ranking),
        "probabilities": list(decision.probabilities),
        "leaderboard": decision_dict["leaderboard"],
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
            "append_only_evaluation_history": True,
        },
    }


def build_adaptive_challenger(state_dir: Path) -> dict[str, object]:
    history_path = state_dir / "canonical_history.json"
    ledger_path = state_dir / "prospective_ledger.json"
    latest_path = state_dir / "latest.json"
    current_path = state_dir / "adaptive_challenger.json"
    history_payload = _load(history_path)
    ledger = _load(ledger_path)
    latest = _load(latest_path)
    records = history_payload.get("records", [])
    if not isinstance(records, list) or not records:
        raise RuntimeError("ADAPTIVE_CANONICAL_HISTORY_EMPTY")

    official_by_contest = _record_map(records)
    existing = _load(current_path) if current_path.exists() else None
    history = _history_from_existing(existing)
    history = [
        _evaluate_entry(item, official_by_contest[int(item["target_contest"])])
        if item.get("evaluation") is None and int(item["target_contest"]) in official_by_contest
        else item
        for item in history
    ]

    training_last = int(records[-1]["contest_id"])
    target = int(latest["next_prediction_target"])
    if target != training_last + 1:
        raise RuntimeError("ADAPTIVE_STATE_TARGET_MISMATCH")

    if existing is not None and int(existing.get("target_contest", -1)) == target:
        current = {
            key: value
            for key, value in existing.items()
            if key not in {"history", "history_summary"}
        }
        current["schema_version"] = 2
        policy = current.get("policy")
        if isinstance(policy, dict):
            policy = dict(policy)
            policy["append_only_evaluation_history"] = True
            current["policy"] = policy
    else:
        current = _build_new_current(
            records=records,
            ledger=ledger,
            latest=latest,
            history_path=history_path,
            ledger_path=ledger_path,
            latest_path=latest_path,
        )

    if not any(int(item.get("target_contest", -1)) == target for item in history):
        history.append(_compact_entry(current))
    history.sort(key=lambda item: int(item["target_contest"]))

    result = dict(current)
    result["history"] = history
    result["history_summary"] = _history_summary(history)
    return result


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
                "history_summary": payload["history_summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
