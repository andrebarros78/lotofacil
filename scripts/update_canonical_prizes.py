from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.ingestion.caixa import CaixaContest, fetch_caixa_contest
from sare_lotofacil.ingestion.validation import validate_contest

SCHEMA_VERSION = 1


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_history(state_dir: Path):
    path = state_dir / "canonical_history.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = tuple(
        validate_contest(int(item["contest_id"]), date.fromisoformat(item["draw_date"]), item["numbers"])
        for item in payload["records"]
    )
    if not records:
        raise RuntimeError("canonical history is empty")
    return {record.contest_id: record for record in records}


def _empty_state() -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "updated_at_utc": None, "contests": []}


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return _empty_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("unsupported canonical prize state schema")
    return state


def _economic_signature(contest: CaixaContest) -> dict[str, object]:
    return {
        "draw_date": contest.record.draw_date.isoformat(),
        "numbers": list(contest.record.numbers),
        "prize_tiers": [
            {"hits": tier.hits, "winners": tier.winners, "prize_cents": tier.prize_cents}
            for tier in contest.prize_tiers
        ],
    }


def _revision_payload(contest: CaixaContest, revision: int) -> dict[str, object]:
    signature = _economic_signature(contest)
    return {
        "revision": revision,
        "captured_at_utc": contest.captured_at.astimezone(timezone.utc).isoformat(),
        "source_url": contest.source_url,
        "raw_payload_sha256": _sha256(contest.raw_payload),
        **signature,
        "economic_signature_sha256": _sha256(signature),
    }


def _upsert_contest(state: dict[str, object], contest: CaixaContest) -> bool:
    contest_id = contest.record.contest_id
    contests = state.setdefault("contests", [])
    entry = next((item for item in contests if int(item["contest_id"]) == contest_id), None)
    signature_hash = _sha256(_economic_signature(contest))
    if entry is None:
        contests.append({"contest_id": contest_id, "revisions": [_revision_payload(contest, 1)]})
        contests.sort(key=lambda item: int(item["contest_id"]))
        return True
    revisions = entry.setdefault("revisions", [])
    if revisions and revisions[-1].get("economic_signature_sha256") == signature_hash:
        return False
    revisions.append(_revision_payload(contest, len(revisions) + 1))
    return True


def update_state(state_dir: Path, *, fetcher=fetch_caixa_contest) -> dict[str, object]:
    state_dir.mkdir(parents=True, exist_ok=True)
    history = _load_history(state_dir)
    latest_contest = max(history)
    path = state_dir / "canonical_prizes.json"
    state = _load_state(path)

    existing_ids = sorted(int(item["contest_id"]) for item in state.get("contests", []))
    first_capture = latest_contest if not existing_ids else existing_ids[-1] + 1
    capture_ids = list(range(first_capture, latest_contest + 1)) if first_capture <= latest_contest else []
    if latest_contest not in capture_ids:
        capture_ids.append(latest_contest)

    changed_ids: list[int] = []
    for contest_id in capture_ids:
        contest = fetcher(contest_id)
        canonical = history.get(contest_id)
        if canonical is None:
            raise RuntimeError(f"official prize contest absent from canonical history: {contest_id}")
        if contest.record.draw_date != canonical.draw_date or contest.record.numbers != canonical.numbers:
            raise RuntimeError(f"official prize state diverges from canonical result: {contest_id}")
        if not contest.prize_tiers:
            raise RuntimeError(f"official contest has no prize tiers: {contest_id}")
        if _upsert_contest(state, contest):
            changed_ids.append(contest_id)

    state["updated_at_utc"] = _utcnow()
    state["latest_contest"] = latest_contest
    state["contest_count"] = len(state.get("contests", []))
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "CANONICAL_PRIZE_STATE_PASS",
        "latest_contest": latest_contest,
        "prize_contests": len(state.get("contests", [])),
        "changed_contests": changed_ids,
        "canonical_prizes_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", default="artifacts/canonical_prize_state.json")
    args = parser.parse_args()
    result = update_state(Path(args.state_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
