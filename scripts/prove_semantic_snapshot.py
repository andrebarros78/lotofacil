from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest
from sare_lotofacil.persistence.repository import (
    create_latest_snapshot,
    persist_history_records,
)
from sare_lotofacil.persistence.snapshot_identity import (
    SEMANTIC_SNAPSHOT_SCHEMA,
    semantic_data_snapshot_hash,
)


def _load_records(path: Path) -> tuple[ContestRecord, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = tuple(
        validate_contest(
            int(item["contest_id"]),
            date.fromisoformat(str(item["draw_date"])),
            tuple(int(value) for value in item["numbers"]),
        )
        for item in payload["records"]
    )
    if not records:
        raise RuntimeError("canonical history is empty")
    if [record.contest_id for record in records] != list(range(1, records[-1].contest_id + 1)):
        raise RuntimeError("canonical history is not contiguous from contest 1")
    return records


def _persist(path: Path, records: tuple[ContestRecord, ...], *, marker: bytes) -> None:
    persist_history_records(
        path,
        records,
        source_url=f"proof://{marker.decode('ascii')}",
        raw_bytes=marker,
        captured_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        source_class="SEMANTIC_SNAPSHOT_PROOF",
        media_type="application/octet-stream",
    )


def _different_numbers(record: ContestRecord) -> tuple[int, ...]:
    candidate = tuple(range(1, 16))
    if candidate == record.numbers:
        candidate = tuple(range(11, 26))
    return candidate


def prove(canonical_path: Path, work_dir: Path) -> dict[str, object]:
    records = _load_records(canonical_path)
    work_dir.mkdir(parents=True, exist_ok=True)
    db_a = work_dir / "rebuild-a.db"
    db_b = work_dir / "rebuild-b.db"
    for path in (db_a, db_b):
        path.unlink(missing_ok=True)
        Path(str(path) + "-wal").unlink(missing_ok=True)
        Path(str(path) + "-shm").unlink(missing_ok=True)

    _persist(db_a, records, marker=b"canonical-a")

    first = records[0]
    divergent = validate_contest(
        first.contest_id,
        first.draw_date,
        _different_numbers(first),
    )
    _persist(db_b, (divergent,), marker=b"temporary-divergence")
    _persist(db_b, records, marker=b"canonical-b")

    snapshot_a = create_latest_snapshot(db_a)
    snapshot_b = create_latest_snapshot(db_b)
    canonical_hash = semantic_data_snapshot_hash(records)

    if snapshot_a.data_snapshot_hash != canonical_hash:
        raise RuntimeError("rebuild A semantic hash diverges from canonical content")
    if snapshot_b.data_snapshot_hash != canonical_hash:
        raise RuntimeError("rebuild B semantic hash diverges from canonical content")
    if snapshot_a.snapshot_hash == snapshot_b.snapshot_hash:
        raise RuntimeError("proof fixture failed to create distinct storage identities")
    if snapshot_a.data_snapshot_hash != snapshot_b.data_snapshot_hash:
        raise RuntimeError("equal canonical data produced different semantic hashes")

    return {
        "status": "SEMANTIC_SNAPSHOT_PROOF_PASS",
        "semantic_schema": SEMANTIC_SNAPSHOT_SCHEMA,
        "canonical_contests": len(records),
        "data_snapshot_hash": canonical_hash,
        "rebuild_a": {
            "storage_snapshot_id": snapshot_a.storage_snapshot_id,
            "storage_snapshot_hash": snapshot_a.storage_snapshot_hash,
            "data_snapshot_hash": snapshot_a.data_snapshot_hash,
        },
        "rebuild_b": {
            "storage_snapshot_id": snapshot_b.storage_snapshot_id,
            "storage_snapshot_hash": snapshot_b.storage_snapshot_hash,
            "data_snapshot_hash": snapshot_b.data_snapshot_hash,
        },
        "assertions": {
            "storage_hashes_differ": True,
            "semantic_hashes_equal": True,
            "canonical_hash_matches_both": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.work_dir.exists():
        shutil.rmtree(args.work_dir)
    result = prove(args.canonical, args.work_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
