from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sare_lotofacil.experiments.joint_backtest import walk_forward_additive_joint
from sare_lotofacil.experiments.joint_models import fit_regularized_additive_joint


def _load_history(path: Path) -> tuple[tuple[int, ...], tuple[int, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("P15_HISTORY_RECORDS_MISSING")

    ordered = sorted(records, key=lambda item: int(item["contest_id"]))
    contest_ids = tuple(int(item["contest_id"]) for item in ordered)
    draws = tuple(tuple(int(number) for number in item["numbers"]) for item in ordered)
    return contest_ids, draws


def build_report(
    history_path: Path,
    *,
    min_train: int,
    prior_strength: float,
) -> dict[str, object]:
    contest_ids, draws = _load_history(history_path)
    result = walk_forward_additive_joint(
        draws,
        min_train=min_train,
        prior_strength=prior_strength,
    )
    fitted = fit_regularized_additive_joint(draws, prior_strength=prior_strength)
    candidate = fitted.map_score()

    summary = asdict(result)
    summary.pop("outcomes", None)
    return {
        "schema_version": 1,
        "status": "P15_JOINT_SCIENCE_REPORT_COMPLETE",
        "program_id": "SARE-P15-ONE-CARD-SCIENCE-V1",
        "hypothesis_id": "P15-H101",
        "history_path": str(history_path),
        "history_contests": len(draws),
        "history_first_contest": contest_ids[0],
        "history_latest_contest": contest_ids[-1],
        "next_target_contest": contest_ids[-1] + 1,
        "walk_forward": summary,
        "next_candidate": {
            "card": list(candidate.card),
            "card_display": " ".join(f"{number:02d}" for number in candidate.card),
            "model_log_probability": candidate.log_probability,
            "model_probability": candidate.probability,
            "model_log_loss_if_exact": candidate.log_loss,
            "role": "EXPERIMENTAL_SINGLE_CARD_MAP",
        },
        "scientific_interpretation": {
            "predictive_evidence": "NOT_ESTABLISHED",
            "candidate_is_guarantee": False,
            "retrospective_success_cannot_promote": True,
            "prospective_freeze_required": True,
            "single_contest_retuning_forbidden": True,
        },
        "purchase_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the P15 joint one-card scientific report.")
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-train", type=int, default=100)
    parser.add_argument("--prior-strength", type=float, default=100.0)
    args = parser.parse_args()

    report = build_report(
        args.history,
        min_train=args.min_train,
        prior_strength=args.prior_strength,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
