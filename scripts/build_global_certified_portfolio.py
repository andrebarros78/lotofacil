from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.coverage import exact_joint_coverage
from sare_lotofacil.portfolios.global_certified_optimizer import (
    GLOBAL_MAX_CARDS,
    GLOBAL_OPTIMIZER_METHOD,
    certify_four_card_native_selection,
    certify_small_global_selection,
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def build_global_certified_portfolio(
    state_dir: Path,
    native_certificate_path: Path,
) -> dict[str, object]:
    latest_path = state_dir / "latest.json"
    challenger_path = state_dir / "adaptive_challenger.json"
    for path in (latest_path, challenger_path, native_certificate_path):
        if not path.exists():
            raise RuntimeError(f"GLOBAL_CERTIFIED_REQUIRED_INPUT_MISSING file={path}")

    latest = _load(latest_path)
    challenger = _load(challenger_path)
    native_certificate = _load(native_certificate_path)
    target = int(latest["next_prediction_target"])
    if int(challenger["target_contest"]) != target:
        raise RuntimeError("GLOBAL_CERTIFIED_TARGET_MISMATCH")
    raw_anchor = challenger.get("card")
    if not isinstance(raw_anchor, list):
        raise RuntimeError("GLOBAL_CERTIFIED_ANCHOR_CARD_MISSING")

    selections = [
        certify_small_global_selection(card_count, anchor_card=raw_anchor)
        for card_count in range(1, GLOBAL_MAX_CARDS)
    ]
    selections.append(
        certify_four_card_native_selection(native_certificate, anchor_card=raw_anchor)
    )

    frontier = [selection.to_dict() for selection in selections]
    max_selection = selections[-1]
    if max_selection.metrics.guaranteed_min_best_hits != 9:
        raise RuntimeError("GLOBAL_CERTIFIED_MAX_BUDGET_FLOOR_REGRESSION")

    independent_enumeration: dict[str, object] = {}
    for threshold in (9, 11, 12, 13, 14, 15):
        exact = exact_joint_coverage(max_selection.cards, min_hits=threshold)
        expected = (
            DEFAULT_RULES.combination_space
            if threshold == 9
            else max_selection.metrics.coverage_count(threshold)
        )
        if exact.covered_outcomes != expected:
            raise RuntimeError(
                "GLOBAL_CERTIFIED_ENUMERATION_MISMATCH "
                f"threshold={threshold} observed={exact.covered_outcomes} expected={expected}"
            )
        independent_enumeration[str(threshold)] = {
            "covered_outcomes": exact.covered_outcomes,
            "total_outcomes": exact.total_outcomes,
            "probability": exact.probability,
            "method": exact.method,
            "independence_assumption_used": exact.independence_assumption_used,
        }

    result: dict[str, object] = {
        "schema_version": 1,
        "status": "GLOBAL_CERTIFIED_BUDGET_PORTFOLIO_PROVEN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "simple_bet_cost_cents": DEFAULT_RULES.simple_bet_cost_cents,
        "full_card_space": DEFAULT_RULES.combination_space,
        "full_result_space": DEFAULT_RULES.combination_space,
        "optimization_method": GLOBAL_OPTIMIZER_METHOD,
        "budget_frontier": frontier,
        "max_budget_cents": GLOBAL_MAX_CARDS * DEFAULT_RULES.simple_bet_cost_cents,
        "max_cards": GLOBAL_MAX_CARDS,
        "max_budget_independent_enumeration": independent_enumeration,
        "native_four_card_certificate": native_certificate,
        "purchase_executed": False,
        "predictive_evidence": "NOT_ESTABLISHED",
        "evidence_label": "OTIMO COMBINATORIO GLOBAL CERTIFICADO — SEM VANTAGEM PREDITIVA COMPROVADA",
        "policy": {
            "future_results_forbidden": True,
            "global_full_space_optimality_proven": True,
            "global_scope": "ALL_DISTINCT_SIMPLE_CARD_PORTFOLIOS_FOR_CARD_COUNTS_1_TO_4",
            "anchor_without_loss_of_generality": True,
            "anchor_reason": (
                "The combinatorial objective is invariant under permutations of the 25-number universe. "
                "Any globally optimal portfolio can therefore be relabeled so one card equals the frozen "
                "adaptive lead card without changing any coverage or maximin metric."
            ),
            "branch_and_price_required": False,
            "equivalent_exact_method": (
                "Exhaustive symmetry quotient over membership histograms. The four-card proof enumerates "
                "all 1,977,452 feasible labeled incidence histograms, proves floor 10 impossible, then "
                "uses exact Johnson-ball union bounds to restrict lower-tier optimization without relaxing "
                "the lexicographic objective."
            ),
            "objective_order": [
                "guaranteed_min_best_hits",
                "coverage_ge_15",
                "coverage_ge_14",
                "coverage_ge_13",
                "coverage_ge_12",
                "coverage_ge_11",
                "mean_best_hits",
            ],
            "spending_requires_operator_action": True,
        },
    }
    result["artifact_sha256"] = _sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--native-certificate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = build_global_certified_portfolio(args.state_dir, args.native_certificate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    maximum = payload["budget_frontier"][-1]
    print(
        json.dumps(
            {
                "status": payload["status"],
                "target_contest": payload["target_contest"],
                "max_budget_cents": payload["max_budget_cents"],
                "max_budget_cards": maximum["cards"],
                "max_budget_floor": maximum["metrics"]["guaranteed_min_best_hits"],
                "max_budget_coverage": maximum["metrics"]["coverage"],
                "max_budget_mean_best_hits": maximum["metrics"]["mean_best_hits"],
                "global_full_space_optimality_proven": payload["policy"]["global_full_space_optimality_proven"],
                "purchase_executed": payload["purchase_executed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
