from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sare_lotofacil.economics import calculate_economic_audit
from sare_lotofacil.portfolios.core import audit_portfolio, generate_uniform_portfolio


def prove(state_dir: Path, *, card_count: int = 10) -> dict[str, object]:
    latest = json.loads((state_dir / "latest.json").read_text(encoding="utf-8"))
    prizes = json.loads((state_dir / "canonical_prizes.json").read_text(encoding="utf-8"))
    contest_id = int(latest["official_latest_contest"])
    entry = next((item for item in prizes["contests"] if int(item["contest_id"]) == contest_id), None)
    if entry is None:
        raise RuntimeError("latest contest missing from canonical prize state")
    revision = entry["revisions"][-1]
    result = tuple(int(value) for value in revision["numbers"])
    tiers = {int(item["hits"]): int(item["prize_cents"]) for item in revision["prize_tiers"]}

    portfolio = generate_uniform_portfolio(card_count, seed=contest_id)
    hits = audit_portfolio(portfolio, result)
    economic = calculate_economic_audit(hits, tiers, theoretical_cost_cents=portfolio.cost_cents)
    if economic.purchase_recorded or economic.actual_cost_cents is not None or economic.actual_net_cents is not None:
        raise RuntimeError("economic proof cannot infer a real purchase")

    identity_payload = {
        "contest_id": contest_id,
        "prize_revision": int(revision["revision"]),
        "seed": portfolio.seed,
        "cards": [list(card) for card in portfolio.cards],
        "economic_signature_sha256": revision["economic_signature_sha256"],
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "status": "GITHUB_ECONOMIC_STATE_PROOF_PASS",
        "contest_id": contest_id,
        "prize_revision": int(revision["revision"]),
        "economic_signature_sha256": revision["economic_signature_sha256"],
        "proof_identity_sha256": identity,
        "card_count": card_count,
        "seed": portfolio.seed,
        "hits": list(economic.hits),
        "prize_by_card_cents": list(economic.prize_by_card_cents),
        "prize_count_by_tier": {str(hits): count for hits, count in economic.prize_count_by_tier},
        "prize_total_cents": economic.prize_total_cents,
        "theoretical_cost_cents": economic.theoretical_cost_cents,
        "hypothetical_net_cents": economic.hypothetical_net_cents,
        "purchase_recorded": economic.purchase_recorded,
        "actual_cost_cents": economic.actual_cost_cents,
        "actual_net_cents": economic.actual_net_cents,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/github_economic_state_proof.json")
    parser.add_argument("--card-count", type=int, default=10)
    args = parser.parse_args()
    result = prove(Path(args.state_dir), card_count=args.card_count)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
