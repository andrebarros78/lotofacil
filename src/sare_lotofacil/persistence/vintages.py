from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.operations import canonical_json
from sare_lotofacil.persistence.repository import SnapshotInfo


def create_snapshot_as_of(path: str | Path, availability_cutoff: datetime) -> SnapshotInfo:
    """Publish an immutable point-in-time snapshot using only then-available revisions.

    Revision numbers express ingestion order, not necessarily information time. The
    selected revision is therefore the most recent ``availability_at`` not later
    than the cutoff, with revision used only as a deterministic tie-breaker.
    Revisions with unknown availability are excluded rather than guessed.
    """
    if availability_cutoff.tzinfo is None:
        raise ValueError("availability_cutoff deve possuir timezone")
    initialize_database(path)
    cutoff = availability_cutoff.isoformat()
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT contest_id, revision, result_mask FROM ("
            "  SELECT contest_id, revision, result_mask, "
            "         ROW_NUMBER() OVER ("
            "           PARTITION BY contest_id "
            "           ORDER BY julianday(availability_at) DESC, revision DESC"
            "         ) AS rn "
            "  FROM contest_revisions "
            "  WHERE availability_at IS NOT NULL "
            "    AND julianday(availability_at) <= julianday(?)"
            ") WHERE rn=1 ORDER BY contest_id",
            (cutoff,),
        ).fetchall()
        if not rows:
            raise ValueError("não há revisões disponíveis no cutoff informado")

        canonical = "as_of=" + cutoff + "\n" + "\n".join(
            f"{contest_id}:{revision}:{result_mask}" for contest_id, revision, result_mask in rows
        )
        snapshot_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        snapshot_id = f"snap-{snapshot_hash[:20]}"
        connection.execute(
            "INSERT OR IGNORE INTO snapshots(snapshot_id, snapshot_hash, state) VALUES (?, ?, 'PUBLISHED')",
            (snapshot_id, snapshot_hash),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO snapshot_members(snapshot_id, contest_id, revision) VALUES (?, ?, ?)",
            [(snapshot_id, contest_id, revision) for contest_id, revision, _ in rows],
        )
        detail = canonical_json(
            {
                "availability_cutoff": cutoff,
                "contest_count": len(rows),
                "selection_policy": "LATEST_AVAILABLE_REVISION_AT_OR_BEFORE_CUTOFF",
                "unknown_availability_policy": "EXCLUDE",
            }
        )
        event_id = "audit-" + hashlib.sha256(
            f"POINT_IN_TIME_SNAPSHOT|snapshot|{snapshot_id}|{detail}".encode("utf-8")
        ).hexdigest()[:24]
        connection.execute(
            "INSERT OR IGNORE INTO audit_events(event_id, action, entity_type, entity_id, detail_json) "
            "VALUES (?, 'POINT_IN_TIME_SNAPSHOT', 'snapshot', ?, ?)",
            (event_id, snapshot_id, detail),
        )
    return SnapshotInfo(snapshot_id, snapshot_hash, len(rows))
