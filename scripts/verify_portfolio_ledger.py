from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _identity(entry: dict[str, object]) -> dict[str, object]:
    return {
        "target_contest": entry["target_contest"],
        "seed": entry["seed"],
        "cards": entry["cards"],
        "theoretical_cost_cents": entry["theoretical_cost_cents"],
        "predictive_evidence": entry["predictive_evidence"],
        "evidence_label": entry["evidence_label"],
        "state_snapshot_id": entry["state_snapshot_id"],
        "state_snapshot_hash": entry["state_snapshot_hash"],
        "protocol_hash": entry["protocol_hash"],
    }


def verify(state_dir: Path) -> dict[str, object]:
    path = state_dir / "portfolio_ledger.json"
    if not path.exists():
        raise RuntimeError("missing operational state file: portfolio_ledger.json")
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != 1:
        raise RuntimeError("unsupported portfolio ledger schema")

    ids: set[str] = set()
    for entry in ledger.get("portfolios", []):
        portfolio_id = str(entry["portfolio_id"])
        if portfolio_id in ids:
            raise RuntimeError(f"duplicate portfolio id: {portfolio_id}")
        ids.add(portfolio_id)
        digest = _sha256(_identity(entry))
        if entry.get("portfolio_sha256") != digest:
            raise RuntimeError(f"portfolio hash mismatch: {portfolio_id}")
        if portfolio_id != f"portfolio-{digest[:24]}":
            raise RuntimeError(f"portfolio id mismatch: {portfolio_id}")
        cards = entry.get("cards") or []
        if not 3 <= len(cards) <= 100:
            raise RuntimeError(f"invalid card count: {portfolio_id}")
        seen_cards: set[tuple[int, ...]] = set()
        for card in cards:
            normalized = tuple(int(value) for value in card)
            if len(normalized) != 15 or len(set(normalized)) != 15:
                raise RuntimeError(f"invalid card cardinality: {portfolio_id}")
            if tuple(sorted(normalized)) != normalized or normalized[0] < 1 or normalized[-1] > 25:
                raise RuntimeError(f"invalid card numbers: {portfolio_id}")
            if normalized in seen_cards:
                raise RuntimeError(f"duplicate card: {portfolio_id}")
            seen_cards.add(normalized)
        expected_cost = len(cards) * DEFAULT_RULES.simple_bet_cost_cents
        if int(entry["theoretical_cost_cents"]) != expected_cost:
            raise RuntimeError(f"theoretical cost mismatch: {portfolio_id}")
        if entry.get("evidence_label") != UNPROVEN_LABEL:
            raise RuntimeError(f"scientific label mismatch: {portfolio_id}")
        purchase = entry.get("purchase") or {}
        if purchase.get("recorded") is False:
            if purchase.get("actual_cost_cents") is not None or purchase.get("recorded_at_utc") is not None or purchase.get("source") is not None:
                raise RuntimeError(f"unrecorded purchase has actual fields: {portfolio_id}")
        elif purchase.get("recorded") is not True:
            raise RuntimeError(f"invalid purchase state: {portfolio_id}")

    return {
        "status": "GITHUB_PORTFOLIO_LEDGER_AUDIT_PASS",
        "portfolio_count": len(ids),
        "portfolio_ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/github_portfolio_ledger_audit.json")
    args = parser.parse_args()
    result = verify(Path(args.state_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
