from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.portfolios.coverage import exact_joint_coverage
from sare_lotofacil.portfolios.coverage_guard import build_two_card_coverage_guard


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_coverage_guard(state_dir: Path) -> dict[str, object]:
    latest_path = state_dir / "latest.json"
    challenger_path = state_dir / "adaptive_challenger.json"
    if not latest_path.exists():
        raise RuntimeError("COVERAGE_GUARD_LATEST_STATE_MISSING")
    if not challenger_path.exists():
        raise RuntimeError("COVERAGE_GUARD_ADAPTIVE_CHALLENGER_MISSING")

    latest = _load(latest_path)
    challenger = _load(challenger_path)
    target = int(latest["next_prediction_target"])
    if int(challenger["target_contest"]) != target:
        raise RuntimeError("COVERAGE_GUARD_TARGET_MISMATCH")

    raw_card = challenger.get("card")
    raw_probabilities = challenger.get("probabilities")
    if not isinstance(raw_card, list):
        raise RuntimeError("COVERAGE_GUARD_LEAD_CARD_MISSING")
    if not isinstance(raw_probabilities, list):
        raise RuntimeError("COVERAGE_GUARD_PROBABILITIES_MISSING")

    decision = build_two_card_coverage_guard(
        raw_card,
        target_contest=target,
        probabilities=raw_probabilities,
    )
    exact = exact_joint_coverage(
        decision.cards,
        min_hits=decision.guaranteed_min_best_hits,
    )
    if exact.covered_outcomes != exact.total_outcomes or exact.probability != 1.0:
        raise RuntimeError("COVERAGE_GUARD_EXACT_PROOF_FAILED")

    return {
        "schema_version": 1,
        "status": "COVERAGE_GUARD_PROVEN",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "role": "COMBINATORIAL_DOWNSIDE_GUARD",
        "lead_source": "ADAPTIVE_CHALLENGER",
        "predictive_evidence": "NOT_REQUIRED_FOR_COMBINATORIAL_GUARANTEE",
        "purchase_executed": False,
        "decision": decision.to_dict(),
        "exact_proof": {
            "min_hits": exact.min_hits,
            "covered_outcomes": exact.covered_outcomes,
            "total_outcomes": exact.total_outcomes,
            "probability": exact.probability,
            "method": exact.method,
            "independence_assumption_used": exact.independence_assumption_used,
        },
        "policy": {
            "future_results_forbidden": True,
            "lead_card_preserved": True,
            "guard_card_additive_only": True,
            "guarantee_scope": "AT_LEAST_ONE_OF_TWO_CARDS_HAS_AT_LEAST_8_HITS_FOR_EVERY_15_OF_25_OUTCOME",
            "jackpot_guarantee": False,
            "spending_requires_operator_action": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = build_coverage_guard(args.state_dir)
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
                "cards": payload["decision"]["cards"],
                "guaranteed_min_best_hits": payload["decision"]["guaranteed_min_best_hits"],
                "covered_outcomes": payload["exact_proof"]["covered_outcomes"],
                "total_outcomes": payload["exact_proof"]["total_outcomes"],
                "purchase_executed": payload["purchase_executed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
