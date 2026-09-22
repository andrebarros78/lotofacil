from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.operational_state import verify_state_commit


def verify(state_dir: Path) -> dict[str, object]:
    state_commit = verify_state_commit(state_dir, allow_legacy=True)
    history_path = state_dir / "canonical_history.json"
    prizes_path = state_dir / "canonical_prizes.json"
    latest_path = state_dir / "latest.json"
    for path in (history_path, prizes_path, latest_path):
        if not path.exists():
            raise RuntimeError(f"missing operational state file: {path.name}")

    history = json.loads(history_path.read_text(encoding="utf-8"))
    records = {
        int(item["contest_id"]): validate_contest(
            int(item["contest_id"]), date.fromisoformat(item["draw_date"]), item["numbers"]
        )
        for item in history["records"]
    }
    prizes = json.loads(prizes_path.read_text(encoding="utf-8"))
    if prizes.get("schema_version") != 1:
        raise RuntimeError("unsupported canonical prize state schema")

    seen: set[int] = set()
    revision_count = 0
    for entry in prizes.get("contests", []):
        contest_id = int(entry["contest_id"])
        if contest_id in seen:
            raise RuntimeError(f"duplicate prize contest: {contest_id}")
        seen.add(contest_id)
        record = records.get(contest_id)
        if record is None:
            raise RuntimeError(f"prize contest absent from canonical history: {contest_id}")
        revisions = entry.get("revisions") or []
        if not revisions:
            raise RuntimeError(f"prize contest has no revisions: {contest_id}")
        expected_revisions = list(range(1, len(revisions) + 1))
        if [int(item["revision"]) for item in revisions] != expected_revisions:
            raise RuntimeError(f"non-contiguous prize revisions: {contest_id}")
        revision_count += len(revisions)
        for revision in revisions:
            if revision["draw_date"] != record.draw_date.isoformat():
                raise RuntimeError(f"prize draw date mismatch: {contest_id}")
            if tuple(int(value) for value in revision["numbers"]) != record.numbers:
                raise RuntimeError(f"prize result mismatch: {contest_id}")
            tiers = revision.get("prize_tiers") or []
            hits = [int(item["hits"]) for item in tiers]
            if hits != [15, 14, 13, 12, 11]:
                raise RuntimeError(f"invalid prize tier coverage/order: {contest_id}")
            for tier in tiers:
                if int(tier["winners"]) < 0 or int(tier["prize_cents"]) < 0:
                    raise RuntimeError(f"invalid prize tier values: {contest_id}")
            signature = {
                "draw_date": revision["draw_date"],
                "numbers": revision["numbers"],
                "prize_tiers": tiers,
            }
            raw = json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            if revision.get("economic_signature_sha256") != digest:
                raise RuntimeError(f"economic signature mismatch: {contest_id}")

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest_contest = int(latest["official_latest_contest"])
    if latest_contest not in seen:
        raise RuntimeError("latest official contest has no canonical prize state")
    if int(prizes.get("latest_contest", -1)) != latest_contest:
        raise RuntimeError("canonical prize latest contest diverges from operational latest")

    return {
        "status": "CANONICAL_PRIZE_AUDIT_PASS",
        "latest_contest": latest_contest,
        "prize_contests": len(seen),
        "state_transaction": state_commit,
        "prize_revisions": revision_count,
        "canonical_prizes_sha256": hashlib.sha256(prizes_path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/canonical_prize_audit.json")
    args = parser.parse_args()
    result = verify(Path(args.state_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
