from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sare_lotofacil.experiments.dynamic_backtest import fit_dynamic_joint, walk_forward_dynamic_joint
from sare_lotofacil.experiments.joint_backtest import walk_forward_additive_joint
from sare_lotofacil.experiments.joint_models import fit_regularized_additive_joint

PREDECLARED_HALF_LIVES = (30.0, 90.0, 180.0, 365.0, 730.0)


def _load_history(path: Path) -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("P15_HISTORY_RECORDS_MISSING")

    ordered = sorted(records, key=lambda item: int(item["contest_id"]))
    contest_ids = tuple(int(item["contest_id"]) for item in ordered)
    draws = tuple(tuple(int(number) for number in item["numbers"]) for item in ordered)
    return contest_ids, draws


def _summary(result) -> dict[str, object]:
    payload = asdict(result)
    payload.pop("outcomes", None)
    return payload


def _candidate_payload(model, *, role: str, discovery_basis: str) -> dict[str, object]:
    candidate = model.map_score()
    return {
        "card": list(candidate.card),
        "card_display": " ".join(f"{number:02d}" for number in candidate.card),
        "model_log_probability": candidate.log_probability,
        "model_probability": candidate.probability,
        "model_log_loss_if_exact": candidate.log_loss,
        "role": role,
        "discovery_basis": discovery_basis,
    }


def build_report(
    history_path: Path,
    *,
    min_train: int,
    prior_strength: float,
) -> dict[str, object]:
    contest_ids, draws = _load_history(history_path)

    static_result = walk_forward_additive_joint(
        draws,
        min_train=min_train,
        prior_strength=prior_strength,
    )
    static_model = fit_regularized_additive_joint(draws, prior_strength=prior_strength)

    dynamic_results = []
    for half_life in PREDECLARED_HALF_LIVES:
        result = walk_forward_dynamic_joint(
            draws,
            half_life=half_life,
            min_train=min_train,
            prior_strength=prior_strength,
        )
        dynamic_results.append(result)

    discovery_winner = max(dynamic_results, key=lambda item: item.mean_joint_log_skill)
    winning_half_life = float(discovery_winner.model_name.rsplit("_", 1)[-1])
    discovery_model = fit_dynamic_joint(
        draws,
        half_life=winning_half_life,
        prior_strength=prior_strength,
    )

    return {
        "schema_version": 2,
        "status": "P15_JOINT_SCIENCE_REPORT_COMPLETE",
        "program_id": "SARE-P15-ONE-CARD-SCIENCE-V1",
        "history_path": str(history_path),
        "history_contests": len(draws),
        "history_first_contest": contest_ids[0],
        "history_latest_contest": contest_ids[-1],
        "next_target_contest": contest_ids[-1] + 1,
        "hypotheses": {
            "P15-H101": {
                "scientific_class": "REGULARIZED_STATIC_ADDITIVE_JOINT",
                "walk_forward": _summary(static_result),
                "next_candidate": _candidate_payload(
                    static_model,
                    role="REJECTED_AS_STANDALONE_PREDICTIVE_CANDIDATE",
                    discovery_basis="FULL_HISTORY_FIT_AFTER_NEGATIVE_WALK_FORWARD_RESULT",
                ),
                "research_decision": "DO_NOT_PROMOTE",
            },
            "P15-H102": {
                "scientific_class": "DYNAMIC_EXPONENTIALLY_WEIGHTED_ADDITIVE_JOINT",
                "predeclared_half_lives": list(PREDECLARED_HALF_LIVES),
                "fixed_model_walk_forward": [_summary(result) for result in dynamic_results],
                "discovery_selection": {
                    "method": "MAX_MEAN_JOINT_LOG_SKILL_OVER_PREDECLARED_DISCOVERY_GRID",
                    "selected_model": discovery_winner.model_name,
                    "selected_mean_joint_log_skill": discovery_winner.mean_joint_log_skill,
                    "selected_joint_log_skill_ci_low": discovery_winner.joint_log_skill_ci_low,
                    "selected_joint_log_skill_ci_high": discovery_winner.joint_log_skill_ci_high,
                    "multiple_testing_adjusted_evidence_claim": False,
                    "role": "DISCOVERY_ONLY_FREEZE_FOR_FUTURE_PROSPECTIVE_TEST",
                },
                "next_candidate": _candidate_payload(
                    discovery_model,
                    role="EXPERIMENTAL_SINGLE_CARD_MAP_TO_FREEZE_PROSPECTIVELY",
                    discovery_basis="PREDECLARED_HALF_LIFE_GRID_RETROSPECTIVE_DISCOVERY_ONLY",
                ),
                "research_decision": "FREEZE_AS_CHALLENGER_ONLY_NOT_CHAMPION",
            },
        },
        "scientific_interpretation": {
            "predictive_evidence": "NOT_ESTABLISHED",
            "single_card_15_is_guaranteed": False,
            "retrospective_model_selection_is_confirmatory_evidence": False,
            "prospective_freeze_required": True,
            "multiple_testing_control_required_before_evidence_claim": True,
            "single_contest_retuning_forbidden": True,
            "future_results_forbidden": True,
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
