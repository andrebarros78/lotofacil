from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sare_lotofacil.domain.masks import mask_to_numbers
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.persistence.db import connect, initialize_database


@dataclass(frozen=True, slots=True)
class PersistedContest:
    contest_id: int
    revision: int
    created: bool
    artifact_id: str


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    snapshot_id: str
    snapshot_hash: str
    contest_count: int


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _artifact_identity(raw_json: str) -> tuple[str, str]:
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    return f"artifact-{digest[:20]}", digest


def persist_caixa_contest(path: str | Path, contest: CaixaContest, *, source_class: str = "OFICIAL_DIRETA") -> PersistedContest:
    initialize_database(path)
    raw_json = _canonical_json(contest.raw_payload)
    artifact_id, digest = _artifact_identity(raw_json)
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO source_artifacts(artifact_id, source_url, source_class, captured_at, sha256, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (artifact_id, contest.source_url, source_class, contest.captured_at.isoformat(), digest, raw_json),
        )
        existing = connection.execute(
            "SELECT revision, draw_date, result_mask FROM contest_revisions WHERE contest_id=? ORDER BY revision DESC",
            (contest.record.contest_id,),
        ).fetchall()
        incoming_tiers = _tier_signature(contest)
        for revision, draw_date, result_mask in existing:
            if draw_date == contest.record.draw_date.isoformat() and result_mask == contest.record.mask:
                stored_tiers = tuple(
                    connection.execute(
                        "SELECT hits, winners, prize_cents FROM prize_tiers "
                        "WHERE contest_id=? AND revision=? ORDER BY hits DESC",
                        (contest.record.contest_id, revision),
                    ).fetchall()
                )
                if stored_tiers == incoming_tiers:
                    return PersistedContest(contest.record.contest_id, revision, False, artifact_id)

        revision = (existing[0][0] + 1) if existing else 1
        connection.execute(
            "INSERT INTO contest_revisions(contest_id, revision, draw_date, result_mask, source_class, source_artifact_id, availability_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                contest.record.contest_id,
                revision,
                contest.record.draw_date.isoformat(),
                contest.record.mask,
                source_class,
                artifact_id,
                contest.captured_at.isoformat(),
            ),
        )
        _replace_prize_tiers(connection, contest.record.contest_id, revision, contest)
        return PersistedContest(contest.record.contest_id, revision, True, artifact_id)


def _tier_signature(contest: CaixaContest) -> tuple[tuple[int, int, int], ...]:
    return tuple((tier.hits, tier.winners, tier.prize_cents) for tier in contest.prize_tiers)


def _replace_prize_tiers(connection: sqlite3.Connection, contest_id: int, revision: int, contest: CaixaContest) -> None:
    connection.execute("DELETE FROM prize_tiers WHERE contest_id=? AND revision=?", (contest_id, revision))
    connection.executemany(
        "INSERT INTO prize_tiers(contest_id, revision, hits, winners, prize_cents) VALUES (?, ?, ?, ?, ?)",
        [(contest_id, revision, *tier) for tier in _tier_signature(contest)],
    )


def create_latest_snapshot(path: str | Path) -> SnapshotInfo:
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT c.contest_id, c.revision, c.result_mask "
            "FROM contest_revisions c "
            "JOIN (SELECT contest_id, MAX(revision) AS revision FROM contest_revisions GROUP BY contest_id) latest "
            "ON latest.contest_id=c.contest_id AND latest.revision=c.revision "
            "ORDER BY c.contest_id"
        ).fetchall()
        if not rows:
            raise ValueError("não há concursos para publicar snapshot")
        canonical = "\n".join(f"{contest_id}:{revision}:{result_mask}" for contest_id, revision, result_mask in rows)
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
        return SnapshotInfo(snapshot_id, snapshot_hash, len(rows))


def load_snapshot_draws(path: str | Path, snapshot_id: str) -> tuple[tuple[int, ...], ...]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT c.result_mask FROM snapshot_members sm "
            "JOIN contest_revisions c ON c.contest_id=sm.contest_id AND c.revision=sm.revision "
            "WHERE sm.snapshot_id=? ORDER BY c.contest_id",
            (snapshot_id,),
        ).fetchall()
    if not rows:
        raise KeyError(f"snapshot inexistente ou vazio: {snapshot_id}")
    return tuple(mask_to_numbers(result_mask) for (result_mask,) in rows)
