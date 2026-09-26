from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sare_lotofacil.experiments.dynamic_backtest import fit_dynamic_joint, walk_forward_dynamic_joint
from sare_lotofacil.experiments.higher_order_backtest import (
    fit_next_higher_order_regime,
    walk_forward_higher_order_regime,
)
from sare_lotofacil.experiments.joint_backtest import walk_forward_additive_joint
from sare_lotofacil.experiments.joint_models import fit_regularized_additive_joint
from sare_lotofacil.experiments.tree_backtest import walk_forward_tree_joint
from sare_lotofacil.experiments.tree_joint import fit_tree_joint

PREDECLARED_HALF_LIVES = (30.0, 90.0, 180.0, 365.0, 730.0)
TREE_PRIOR_STRENGTH = 20.0
HIGHER_ORDER_PRIOR_STRENGTH = 32.0
HIGHER_ORDER_RECENT_WINDOW = 180
HIGHER_ORDER_SELECTOR_ALPHA = 0.05
HIGHER_ORDER_SWITCH_MARGIN = 0.0
FULL_SPACE_TOP_K = 10


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


def _decision_from_result(result) -> str:
    if result.mean_joint_log_skill > 0.0 and result.joint_log_skill_ci_low > 0.0:
        return "DOMAIN_SIGNAL_UNDER_TEST_RETROSPECTIVE_ONLY"
    return "DO_NOT_PROMOTE"


def _ranking_payload(ranking) -> dict[str, object]:
    return {
        "evaluated_cards": ranking.evaluated_cards,
        "top_k": len(ranking.top_cards),
        "top_cards": [
            {
                "rank": index,
                "card": list(score.card),
                "card_display": " ".join(f"{number:02d}" for number in score.card),
                "log_probability": score.log_probability,
                "probability": score.probability,
            }
            for index, score in enumerate(ranking.top_cards, start=1)
        ],
        "observed_card": list(ranking.observed_card) if ranking.observed_card is not None else None,
        "observed_rank": ranking.observed_rank,
        "global_top1_certified_by_exhaustive_enumeration": True,
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

    dynamic_discovery_winner = max(dynamic_results, key=lambda item: item.mean_joint_log_skill)
    winning_half_life = float(dynamic_discovery_winner.model_name.rsplit("_", 1)[-1])
    dynamic_discovery_model = fit_dynamic_joint(
        draws,
        half_life=winning_half_life,
        prior_strength=prior_strength,
    )

    tree_result = walk_forward_tree_joint(
        draws,
        min_train=min_train,
        prior_strength=TREE_PRIOR_STRENGTH,
    )
    tree_model = fit_tree_joint(draws, prior_strength=TREE_PRIOR_STRENGTH)
    tree_decision = _decision_from_result(tree_result)

    higher_order_result = walk_forward_higher_order_regime(
        draws,
        min_train=min_train,
        prior_strength=HIGHER_ORDER_PRIOR_STRENGTH,
        recent_window=HIGHER_ORDER_RECENT_WINDOW,
        selector_alpha=HIGHER_ORDER_SELECTOR_ALPHA,
        switch_margin=HIGHER_ORDER_SWITCH_MARGIN,
    )
    higher_order_model, next_regime = fit_next_higher_order_regime(
        draws,
        min_train=min_train,
        prior_strength=HIGHER_ORDER_PRIOR_STRENGTH,
        recent_window=HIGHER_ORDER_RECENT_WINDOW,
        selector_alpha=HIGHER_ORDER_SELECTOR_ALPHA,
        switch_margin=HIGHER_ORDER_SWITCH_MARGIN,
    )
    higher_order_decision = _decision_from_result(higher_order_result)

    # The final/current H104 model is ranked over the complete state space once.
    # Historical windows use exact DP MAP to keep the walk-forward computationally bounded.
    full_ranking = higher_order_model.rank_full_space(top_k=FULL_SPACE_TOP_K)
    if full_ranking.evaluated_cards != 3_268_760:
        raise RuntimeError("P15_H104_FULL_SPACE_RANK_INCOMPLETE")
    if not full_ranking.top_cards or full_ranking.top_cards[0].card != higher_order_model.map_card():
        raise RuntimeError("P15_H104_DP_MAP_DISAGREES_WITH_EXHAUSTIVE_RANK")

    return {
        "schema_version": 4,
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
                    "selected_model": dynamic_discovery_winner.model_name,
                    "selected_mean_joint_log_skill": dynamic_discovery_winner.mean_joint_log_skill,
                    "selected_joint_log_skill_ci_low": dynamic_discovery_winner.joint_log_skill_ci_low,
                    "selected_joint_log_skill_ci_high": dynamic_discovery_winner.joint_log_skill_ci_high,
                    "multiple_testing_adjusted_evidence_claim": False,
                    "role": "DISCOVERY_ONLY",
                },
                "next_candidate": _candidate_payload(
                    dynamic_discovery_model,
                    role="EXPERIMENTAL_SINGLE_CARD_MAP_NO_PROMOTION",
                    discovery_basis="PREDECLARED_HALF_LIFE_GRID_RETROSPECTIVE_DISCOVERY_ONLY",
                ),
                "research_decision": "DO_NOT_PROMOTE",
            },
            "P15-H103": {
                "scientific_class": "CHOW_LIU_PAIRWISE_TREE_FIXED_CARDINALITY",
                "mechanism": "PAIRWISE_MUTUAL_INFORMATION_TREE_WITH_EXACT_15_OF_25_CONDITIONING",
                "prior_strength": TREE_PRIOR_STRENGTH,
                "walk_forward": _summary(tree_result),
                "next_candidate": _candidate_payload(
                    tree_model,
                    role=(
                        "EXPERIMENTAL_SINGLE_CARD_MAP_TO_FREEZE_PROSPECTIVELY"
                        if tree_decision != "DO_NOT_PROMOTE"
                        else "REJECTED_AS_STANDALONE_PREDICTIVE_CANDIDATE"
                    ),
                    discovery_basis="FULL_PREQUENTIAL_HISTORY_PAIRWISE_TREE",
                ),
                "research_decision": tree_decision,
            },
            "P15-H104": {
                "scientific_class": "HIGHER_ORDER_BLOCK_FACTOR_WITH_PREQUENTIAL_REGIME_SELECTION",
                "mechanism": (
                    "PAST_ONLY_INFORMATION_BLOCKS_PLUS_COMPLETE_5BIT_PATTERN_FACTORS_"
                    "CONDITIONED_ON_EXACT_15_WITH_LONG_RECENT_HARD_REGIME_SWITCH"
                ),
                "interaction_order_supported_within_blocks": [2, 3, 4, 5],
                "prior_strength": HIGHER_ORDER_PRIOR_STRENGTH,
                "recent_window": HIGHER_ORDER_RECENT_WINDOW,
                "selector_alpha": HIGHER_ORDER_SELECTOR_ALPHA,
                "switch_margin": HIGHER_ORDER_SWITCH_MARGIN,
                "block_partition_frozen_from_initial_training_window": True,
                "walk_forward": _summary(higher_order_result),
                "next_regime_decision": asdict(next_regime),
                "next_candidate": _candidate_payload(
                    higher_order_model,
                    role=(
                        "EXPERIMENTAL_SINGLE_CARD_MAP_TO_FREEZE_PROSPECTIVELY"
                        if higher_order_decision != "DO_NOT_PROMOTE"
                        else "REJECTED_AS_STANDALONE_PREDICTIVE_CANDIDATE"
                    ),
                    discovery_basis="PREQUENTIAL_HIGHER_ORDER_REGIME_ENGINE",
                ),
                "full_space_ranking": _ranking_payload(full_ranking),
                "research_decision": higher_order_decision,
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
            "failed_hypotheses_receive_zero_champion_weight": True,
            "higher_order_full_space_ranker_exact": True,
            "higher_order_full_space_size": 3_268_760,
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
