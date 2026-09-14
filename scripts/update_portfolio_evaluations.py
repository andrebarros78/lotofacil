from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.economics import calculate_economic_audit
from sare_lotofacil.portfolios.core import Portfolio, audit_portfolio


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_evaluations(state_dir: Path) -> dict[str, object]:
    ledger_path = state_dir / "portfolio_ledger.json"
    if not ledger_path.exists():
        return {"status": "GITHUB_PORTFOLIO_EVALUATION_PASS", "evaluated": [], "unchanged": []}

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    history = json.loads((state_dir / "canonical_history.json").read_text(encoding="utf-8"))
    prizes = json.loads((state_dir / "canonical_prizes.json").read_text(encoding="utf-8"))
    history_by_id = {int(item["contest_id"]): item for item in history["records"]}
    prizes_by_id = {int(item["contest_id"]): item for item in prizes["contests"]}

    evaluated: list[str] = []
    unchanged: list[str] = []
    for entry in ledger.get("portfolios", []):
        portfolio_id = str(entry["portfolio_id"])
        target = int(entry["target_contest"])
        result = history_by_id.get(target)
        prize_entry = prizes_by_id.get(target)
        if result is None or prize_entry is None:
            unchanged.append(portfolio_id)
            continue
        prize_revision = prize_entry["revisions"][-1]
        input_identity = {
            "target_contest": target,
            "draw_date": result["draw_date"],
            "numbers": result["numbers"],
            "prize_revision": int(prize_revision["revision"]),
            "economic_signature_sha256": prize_revision["economic_signature_sha256"],
        }
        input_sha = _sha256(input_identity)
        evaluations = entry.setdefault("evaluations", [])
        if evaluations and evaluations[-1].get("evaluation_input_sha256") == input_sha:
            unchanged.append(portfolio_id)
            continue

        cards = tuple(tuple(int(value) for value in card) for card in entry["cards"])
        portfolio = Portfolio(
            seed=int(entry["seed"]),
            cards=cards,
            cost_cents=int(entry["theoretical_cost_cents"]),
            evidence_label=str(entry["evidence_label"]),
        )
        hits = audit_portfolio(portfolio, result["numbers"])
        tiers = {int(item["hits"]): int(item["prize_cents"]) for item in prize_revision["prize_tiers"]}
        economic = calculate_economic_audit(
            hits,
            tiers,
            theoretical_cost_cents=int(entry["theoretical_cost_cents"]),
        )
        purchase = entry.get("purchase") or {}
        purchase_recorded = purchase.get("recorded") is True
        actual_cost = int(purchase["actual_cost_cents"]) if purchase_recorded else None
        actual_net = economic.prize_total_cents - actual_cost if actual_cost is not None else None
        evaluation = {
            "evaluation_revision": len(evaluations) + 1,
            "evaluated_at_utc": _utcnow(),
            "evaluation_input_sha256": input_sha,
            "target_contest": target,
            "draw_date": result["draw_date"],
            "result_numbers": [int(value) for value in result["numbers"]],
            "prize_revision": int(prize_revision["revision"]),
            "economic_signature_sha256": prize_revision["economic_signature_sha256"],
            "hits": list(economic.hits),
            "prize_by_card_cents": list(economic.prize_by_card_cents),
            "prize_count_by_tier": {str(tier): count for tier, count in economic.prize_count_by_tier},
            "prize_total_cents": economic.prize_total_cents,
            "theoretical_cost_cents": economic.theoretical_cost_cents,
            "hypothetical_net_cents": economic.hypothetical_net_cents,
            "purchase_recorded": purchase_recorded,
            "actual_cost_cents": actual_cost,
            "actual_net_cents": actual_net,
        }
        evaluation["evaluation_sha256"] = _sha256({key: value for key, value in evaluation.items() if key not in {"evaluated_at_utc", "evaluation_sha256"}})
        evaluations.append(evaluation)
        evaluated.append(portfolio_id)

    if evaluated:
        ledger["updated_at_utc"] = _utcnow()
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "GITHUB_PORTFOLIO_EVALUATION_PASS",
        "evaluated": evaluated,
        "unchanged": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/github_portfolio_evaluation.json")
    args = parser.parse_args()
    result = update_evaluations(Path(args.state_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
