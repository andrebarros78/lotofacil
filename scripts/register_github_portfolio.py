from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.portfolios.core import UNPROVEN_LABEL, generate_uniform_portfolio

SCHEMA_VERSION = 1


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _empty_ledger() -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "updated_at_utc": None, "portfolios": []}


def _load_ledger(path: Path) -> dict[str, object]:
    if not path.exists():
        return _empty_ledger()
    ledger = _load(path)
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported portfolio ledger schema")
    return ledger


def register_portfolio(
    state_dir: Path,
    *,
    card_count: int,
    seed: int,
    target_contest: int = 0,
    source_code_sha: str,
    operations_state_parent_sha: str,
) -> dict[str, object]:
    latest = _load(state_dir / "latest.json")
    prospective = _load(state_dir / "prospective_ledger.json")
    next_target = int(latest["next_prediction_target"])
    effective_target = next_target if target_contest == 0 else int(target_contest)
    if effective_target != next_target:
        raise ValueError(f"carteira canônica só pode mirar o próximo concurso congelado: {next_target}")

    effective_seed = effective_target if seed == 0 else int(seed)
    portfolio = generate_uniform_portfolio(card_count, seed=effective_seed)
    if portfolio.evidence_label != UNPROVEN_LABEL:
        raise RuntimeError("portfolio evidence label invariant violated")

    predictive_evidence = latest["prospective"]["predictive_evidence"]
    protocol_hash = prospective["protocol"]["protocol_hash"]
    identity = {
        "target_contest": effective_target,
        "seed": portfolio.seed,
        "cards": [list(card) for card in portfolio.cards],
        "theoretical_cost_cents": portfolio.cost_cents,
        "predictive_evidence": predictive_evidence,
        "evidence_label": portfolio.evidence_label,
        "state_snapshot_id": latest["snapshot_id"],
        "state_snapshot_hash": latest["snapshot_hash"],
        "protocol_hash": protocol_hash,
    }
    digest = _sha256(identity)
    portfolio_id = f"portfolio-{digest[:24]}"

    ledger_path = state_dir / "portfolio_ledger.json"
    ledger = _load_ledger(ledger_path)
    existing = next((item for item in ledger["portfolios"] if item["portfolio_id"] == portfolio_id), None)
    if existing is not None:
        if existing.get("portfolio_sha256") != digest:
            raise RuntimeError("portfolio id collision")
        return {
            "status": "GITHUB_PORTFOLIO_REGISTER_PASS",
            "created": False,
            "portfolio_id": portfolio_id,
            "portfolio_sha256": digest,
            "target_contest": effective_target,
        }

    entry = {
        "portfolio_id": portfolio_id,
        "portfolio_sha256": digest,
        "created_at_utc": _utcnow(),
        "source_code_sha": source_code_sha,
        "operations_state_parent_sha": operations_state_parent_sha,
        **identity,
        "purchase": {
            "recorded": False,
            "actual_cost_cents": None,
            "recorded_at_utc": None,
            "source": None,
        },
        "evaluations": [],
    }
    ledger["portfolios"].append(entry)
    ledger["portfolios"].sort(key=lambda item: (int(item["target_contest"]), item["portfolio_id"]))
    ledger["updated_at_utc"] = _utcnow()
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "GITHUB_PORTFOLIO_REGISTER_PASS",
        "created": True,
        "portfolio_id": portfolio_id,
        "portfolio_sha256": digest,
        "target_contest": effective_target,
        "card_count": len(portfolio.cards),
        "theoretical_cost_cents": portfolio.cost_cents,
        "purchase_recorded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--card-count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--target-contest", type=int, default=0)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--operations-state-parent-sha", required=True)
    parser.add_argument("--out", default="artifacts/github_portfolio_register.json")
    args = parser.parse_args()
    result = register_portfolio(
        Path(args.state_dir),
        card_count=args.card_count,
        seed=args.seed,
        target_contest=args.target_contest,
        source_code_sha=args.source_code_sha,
        operations_state_parent_sha=args.operations_state_parent_sha,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
