from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.authority import operator_card_for_generation_index
from sare_lotofacil.portfolios.coverage import exact_joint_coverage
from sare_lotofacil.portfolios.coverage_guard import build_two_card_coverage_guard
from sare_lotofacil.portfolios.exact_budget_optimizer import (
    MAX_EXACT_CANDIDATE_POOL,
    MAX_EXACT_OPTIMIZER_CARDS,
    optimize_budget_exact,
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _append_candidate(
    cards: list[tuple[int, ...]],
    sources: list[str],
    card: object,
    source: str,
) -> None:
    if not isinstance(card, list):
        return
    normalized = tuple(sorted(int(number) for number in card))
    if len(normalized) != DEFAULT_RULES.simple_card_size or len(set(normalized)) != len(normalized):
        raise RuntimeError(f"EXACT_BUDGET_CANDIDATE_INVALID source={source}")
    if normalized not in cards:
        cards.append(normalized)
        sources.append(source)


def _candidate_pool(
    *,
    target: int,
    challenger: dict[str, object],
    guard_card: tuple[int, ...],
) -> tuple[tuple[tuple[int, ...], ...], tuple[str, ...]]:
    cards: list[tuple[int, ...]] = []
    sources: list[str] = []

    _append_candidate(cards, sources, challenger.get("card"), "ADAPTIVE_CHALLENGER_LEAD")
    _append_candidate(cards, sources, list(guard_card), "TWO_CARD_COVERAGE_GUARD")

    champion = challenger.get("champion_control")
    if isinstance(champion, dict):
        _append_candidate(cards, sources, champion.get("card"), "PROSPECTIVE_CHAMPION_CONTROL")

    generation_index = 0
    while len(cards) < MAX_EXACT_CANDIDATE_POOL:
        card = operator_card_for_generation_index(target, generation_index)
        generation_index += 1
        if card in cards:
            continue
        cards.append(card)
        sources.append(f"DETERMINISTIC_OPERATOR_INDEX_{generation_index - 1}")

    return tuple(cards), tuple(sources)


def build_exact_budget_portfolio(state_dir: Path) -> dict[str, object]:
    latest_path = state_dir / "latest.json"
    challenger_path = state_dir / "adaptive_challenger.json"
    for path in (latest_path, challenger_path):
        if not path.exists():
            raise RuntimeError(f"EXACT_BUDGET_REQUIRED_STATE_MISSING file={path.name}")

    latest = _load(latest_path)
    challenger = _load(challenger_path)
    target = int(latest["next_prediction_target"])
    if int(challenger["target_contest"]) != target:
        raise RuntimeError("EXACT_BUDGET_TARGET_MISMATCH")

    raw_card = challenger.get("card")
    raw_probabilities = challenger.get("probabilities")
    if not isinstance(raw_card, list) or not isinstance(raw_probabilities, list):
        raise RuntimeError("EXACT_BUDGET_CHALLENGER_PAYLOAD_INVALID")
    guard_decision = build_two_card_coverage_guard(
        raw_card,
        target_contest=target,
        probabilities=raw_probabilities,
    )

    candidates, sources = _candidate_pool(
        target=target,
        challenger=challenger,
        guard_card=guard_decision.guard_card,
    )
    candidate_payload = [
        {"index": index, "source": sources[index], "card": list(card)}
        for index, card in enumerate(candidates)
    ]
    candidate_pool_sha256 = _sha256(candidate_payload)

    frontier: list[dict[str, object]] = []
    for card_count in range(1, MAX_EXACT_OPTIMIZER_CARDS + 1):
        budget_cents = card_count * DEFAULT_RULES.simple_bet_cost_cents
        selection = optimize_budget_exact(
            candidates,
            budget_cents=budget_cents,
            mandatory_indices=(0,),
        )
        frontier.append(selection.to_dict())

    max_selection = frontier[-1]
    max_cards = tuple(tuple(int(number) for number in card) for card in max_selection["cards"])
    metrics = max_selection["metrics"]
    if not isinstance(metrics, dict):
        raise RuntimeError("EXACT_BUDGET_METRICS_MISSING")
    coverage = metrics.get("coverage")
    if not isinstance(coverage, dict):
        raise RuntimeError("EXACT_BUDGET_COVERAGE_MISSING")

    thresholds = sorted({
        int(metrics["guaranteed_min_best_hits"]),
        11,
        12,
        13,
        14,
        15,
    })
    enumeration_proof: dict[str, object] = {}
    for threshold in thresholds:
        exact = exact_joint_coverage(max_cards, min_hits=threshold)
        if threshold >= 11:
            expected = int(coverage[str(threshold)]["covered_outcomes"])
        else:
            expected = exact.total_outcomes
        if exact.covered_outcomes != expected:
            raise RuntimeError(
                "EXACT_BUDGET_DP_ENUMERATION_MISMATCH "
                f"threshold={threshold} dp={expected} enumeration={exact.covered_outcomes}"
            )
        enumeration_proof[str(threshold)] = {
            "covered_outcomes": exact.covered_outcomes,
            "total_outcomes": exact.total_outcomes,
            "probability": exact.probability,
            "method": exact.method,
            "independence_assumption_used": exact.independence_assumption_used,
        }

    result = {
        "schema_version": 1,
        "status": "EXACT_BUDGET_PORTFOLIO_PROVEN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "simple_bet_cost_cents": DEFAULT_RULES.simple_bet_cost_cents,
        "full_result_space": DEFAULT_RULES.combination_space,
        "full_card_space": DEFAULT_RULES.combination_space,
        "coverage_guard_decision": guard_decision.to_dict(),
        "candidate_pool": candidate_payload,
        "candidate_pool_sha256": candidate_pool_sha256,
        "budget_frontier": frontier,
        "max_exact_budget_cents": MAX_EXACT_OPTIMIZER_CARDS * DEFAULT_RULES.simple_bet_cost_cents,
        "max_exact_cards": MAX_EXACT_OPTIMIZER_CARDS,
        "max_budget_enumeration_proof": enumeration_proof,
        "purchase_executed": False,
        "predictive_evidence": "NOT_ESTABLISHED",
        "policy": {
            "future_results_forbidden": True,
            "mandatory_lead_card": True,
            "candidate_pool_optimality_proven": True,
            "global_full_space_optimality_proven": False,
            "global_limit_reason": (
                "The optimizer exhaustively proves the best subset only inside the declared candidate pool. "
                "It does not claim exhaustive subset search across all 3,268,760 possible cards."
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
            "budget_mode": "SIMPLE_CARD_COUNT_FRONTIER_1_TO_4",
            "spending_requires_operator_action": True,
        },
    }
    result["artifact_sha256"] = _sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = build_exact_budget_portfolio(args.state_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    max_selection = payload["budget_frontier"][-1]
    print(
        json.dumps(
            {
                "status": payload["status"],
                "target_contest": payload["target_contest"],
                "candidate_pool_size": len(payload["candidate_pool"]),
                "max_exact_budget_cents": payload["max_exact_budget_cents"],
                "max_budget_cards": max_selection["cards"],
                "max_budget_floor": max_selection["metrics"]["guaranteed_min_best_hits"],
                "max_budget_coverage": max_selection["metrics"]["coverage"],
                "purchase_executed": payload["purchase_executed"],
                "global_full_space_optimality_proven": payload["policy"]["global_full_space_optimality_proven"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
