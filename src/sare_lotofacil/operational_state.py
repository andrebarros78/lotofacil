from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

STATE_COMMIT_FILE = "state_commit.json"
TXN_POINTER_FILE = ".state_transaction.json"
TXN_DIR = ".state-txn"
STATE_TXN_SCHEMA = "operational-state-transaction-v1"
STATE_COMMIT_SCHEMA = "operational-state-commit-v1"


class StateTransactionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StateCommit:
    generation_id: str
    files: dict[str, str]
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": STATE_COMMIT_SCHEMA,
            "generation_id": self.generation_id,
            "committed_at_utc": self.metadata["committed_at_utc"],
            "files": dict(sorted(self.files.items())),
            "metadata": {
                key: value
                for key, value in sorted(self.metadata.items())
                if key != "committed_at_utc"
            },
        }


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    _fsync_dir(path.parent)


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_bytes(path, _canonical_bytes(payload))


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StateTransactionError(f"invalid JSON object: {path}")
    return payload


def _transaction_pointer_path(state_dir: Path) -> Path:
    return state_dir / TXN_POINTER_FILE


def _transaction_root(state_dir: Path, generation_id: str) -> Path:
    return state_dir / TXN_DIR / generation_id


def _manifest_path(state_dir: Path, generation_id: str) -> Path:
    return _transaction_root(state_dir, generation_id) / "manifest.json"


def _old_path(state_dir: Path, generation_id: str, relative: str) -> Path:
    return _transaction_root(state_dir, generation_id) / "old" / relative


def _new_path(state_dir: Path, generation_id: str, relative: str) -> Path:
    return _transaction_root(state_dir, generation_id) / "new" / relative


def _normalize_files(files: Mapping[str, bytes]) -> dict[str, bytes]:
    normalized: dict[str, bytes] = {}
    for relative, content in files.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"invalid operational state path: {relative}")
        key = path.as_posix()
        if key in {STATE_COMMIT_FILE, TXN_POINTER_FILE} or key.startswith(f"{TXN_DIR}/"):
            raise ValueError(f"reserved operational state path: {relative}")
        normalized[key] = bytes(content)
    if not normalized:
        raise ValueError("state transaction requires at least one file")
    return normalized


def _build_manifest(
    state_dir: Path,
    generation_id: str,
    files: Mapping[str, bytes],
) -> dict[str, object]:
    entries: dict[str, object] = {}
    for relative, content in sorted(files.items()):
        target = state_dir / relative
        old_exists = target.exists()
        old_hash = _sha256_bytes(target.read_bytes()) if old_exists else None
        entries[relative] = {
            "old_exists": old_exists,
            "old_sha256": old_hash,
            "new_sha256": _sha256_bytes(content),
        }
    return {
        "schema": STATE_TXN_SCHEMA,
        "generation_id": generation_id,
        "files": entries,
    }


def _stage_transaction(
    state_dir: Path,
    generation_id: str,
    files: Mapping[str, bytes],
) -> dict[str, object]:
    root = _transaction_root(state_dir, generation_id)
    if root.exists():
        raise StateTransactionError(f"transaction directory already exists: {generation_id}")
    (root / "old").mkdir(parents=True, exist_ok=False)
    (root / "new").mkdir(parents=True, exist_ok=False)

    manifest = _build_manifest(state_dir, generation_id, files)
    for relative, content in sorted(files.items()):
        target = state_dir / relative
        old = _old_path(state_dir, generation_id, relative)
        new = _new_path(state_dir, generation_id, relative)
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.copyfile(target, old)
            with old.open("rb") as handle:
                os.fsync(handle.fileno())
        atomic_write_bytes(new, content)

    atomic_write_json(_manifest_path(state_dir, generation_id), manifest)
    atomic_write_json(
        _transaction_pointer_path(state_dir),
        {
            "schema": STATE_TXN_SCHEMA,
            "generation_id": generation_id,
            "phase": "PREPARED",
        },
    )
    return manifest


def _read_commit(state_dir: Path) -> dict[str, object] | None:
    path = state_dir / STATE_COMMIT_FILE
    if not path.exists():
        return None
    return _load_json(path)


def _committed_generation(state_dir: Path) -> str | None:
    commit = _read_commit(state_dir)
    if commit is None:
        return None
    if commit.get("schema") != STATE_COMMIT_SCHEMA:
        raise StateTransactionError("state commit schema mismatch")
    generation = commit.get("generation_id")
    if not isinstance(generation, str) or not generation:
        raise StateTransactionError("state commit generation missing")
    return generation


def _restore_old(state_dir: Path, manifest: Mapping[str, object]) -> None:
    generation_id = str(manifest["generation_id"])
    entries = manifest["files"]
    if not isinstance(entries, dict):
        raise StateTransactionError("transaction manifest files invalid")
    for relative, raw_entry in sorted(entries.items()):
        if not isinstance(raw_entry, dict):
            raise StateTransactionError("transaction manifest entry invalid")
        target = state_dir / relative
        old_exists = bool(raw_entry["old_exists"])
        if old_exists:
            old = _old_path(state_dir, generation_id, relative)
            expected = raw_entry.get("old_sha256")
            if not old.exists() or _sha256_bytes(old.read_bytes()) != expected:
                raise StateTransactionError(f"old backup invalid: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, target)
            _fsync_dir(target.parent)
        elif target.exists():
            target.unlink()
            _fsync_dir(target.parent)


def _complete_new(state_dir: Path, manifest: Mapping[str, object]) -> None:
    generation_id = str(manifest["generation_id"])
    entries = manifest["files"]
    if not isinstance(entries, dict):
        raise StateTransactionError("transaction manifest files invalid")
    for relative, raw_entry in sorted(entries.items()):
        if not isinstance(raw_entry, dict):
            raise StateTransactionError("transaction manifest entry invalid")
        target = state_dir / relative
        expected = str(raw_entry["new_sha256"])
        if target.exists() and _sha256_bytes(target.read_bytes()) == expected:
            continue
        new = _new_path(state_dir, generation_id, relative)
        if not new.exists() or _sha256_bytes(new.read_bytes()) != expected:
            raise StateTransactionError(f"new staged file invalid: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(new, target)
        with target.open("rb") as handle:
            os.fsync(handle.fileno())
        _fsync_dir(target.parent)


def recover_state_transaction(state_dir: Path) -> str:
    state_dir.mkdir(parents=True, exist_ok=True)
    pointer = _transaction_pointer_path(state_dir)
    if not pointer.exists():
        return "CLEAN"

    pointer_payload = _load_json(pointer)
    generation_id = pointer_payload.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id:
        raise StateTransactionError("transaction pointer generation missing")
    manifest = _load_json(_manifest_path(state_dir, generation_id))
    committed = _committed_generation(state_dir)

    if committed == generation_id:
        _complete_new(state_dir, manifest)
        outcome = "COMMITTED_COMPLETED"
    else:
        _restore_old(state_dir, manifest)
        outcome = "PREPARED_ROLLED_BACK"

    pointer.unlink(missing_ok=True)
    shutil.rmtree(_transaction_root(state_dir, generation_id), ignore_errors=False)
    txn_parent = state_dir / TXN_DIR
    if txn_parent.exists() and not any(txn_parent.iterdir()):
        txn_parent.rmdir()
    _fsync_dir(state_dir)
    return outcome


def verify_state_commit(state_dir: Path, *, allow_legacy: bool = True) -> dict[str, object]:
    recover_state_transaction(state_dir)
    commit = _read_commit(state_dir)
    if commit is None:
        if allow_legacy:
            return {
                "status": "LEGACY_STATE_WITHOUT_TRANSACTION_COMMIT",
                "generation_id": None,
                "verified_files": 0,
            }
        raise StateTransactionError("state commit missing")
    if commit.get("schema") != STATE_COMMIT_SCHEMA:
        raise StateTransactionError("state commit schema mismatch")
    files = commit.get("files")
    if not isinstance(files, dict) or not files:
        raise StateTransactionError("state commit file map missing")
    for relative, expected in files.items():
        path = state_dir / str(relative)
        if not path.exists():
            raise StateTransactionError(f"committed state file missing: {relative}")
        observed = _sha256_bytes(path.read_bytes())
        if observed != expected:
            raise StateTransactionError(f"committed state file hash mismatch: {relative}")
    return {
        "status": "STATE_COMMIT_VERIFIED",
        "generation_id": commit["generation_id"],
        "verified_files": len(files),
        "metadata": commit.get("metadata", {}),
    }


def publish_state_transaction(
    state_dir: Path,
    files: Mapping[str, bytes],
    *,
    metadata: Mapping[str, object] | None = None,
    generation_id: str | None = None,
    crash_after_replace: int | None = None,
    crash_after_commit: bool = False,
) -> dict[str, object]:
    state_dir.mkdir(parents=True, exist_ok=True)
    recover_state_transaction(state_dir)
    normalized = _normalize_files(files)
    generation = generation_id or f"state-{uuid.uuid4().hex}"
    manifest = _stage_transaction(state_dir, generation, normalized)
    entries = manifest["files"]
    assert isinstance(entries, dict)

    replaced = 0
    for relative in sorted(normalized):
        new = _new_path(state_dir, generation, relative)
        target = state_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(new, target)
        _fsync_dir(target.parent)
        replaced += 1
        if crash_after_replace is not None and replaced == crash_after_replace:
            raise StateTransactionError(
                f"INJECTED_CRASH_AFTER_REPLACE_{crash_after_replace}"
            )

    hashes = {
        relative: str(entry["new_sha256"])
        for relative, entry in sorted(entries.items())
        if isinstance(entry, dict)
    }
    commit_metadata = {
        "committed_at_utc": datetime.now(timezone.utc).isoformat(),
        **dict(metadata or {}),
    }
    commit = StateCommit(generation, hashes, commit_metadata)
    atomic_write_json(state_dir / STATE_COMMIT_FILE, commit.to_dict())

    if crash_after_commit:
        raise StateTransactionError("INJECTED_CRASH_AFTER_COMMIT")

    pointer = _transaction_pointer_path(state_dir)
    pointer.unlink(missing_ok=True)
    shutil.rmtree(_transaction_root(state_dir, generation), ignore_errors=False)
    txn_parent = state_dir / TXN_DIR
    if txn_parent.exists() and not any(txn_parent.iterdir()):
        txn_parent.rmdir()
    _fsync_dir(state_dir)
    verify_state_commit(state_dir, allow_legacy=False)
    return commit.to_dict()
