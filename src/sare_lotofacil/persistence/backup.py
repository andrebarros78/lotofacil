from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sare_lotofacil.persistence.db import connect


@dataclass(frozen=True, slots=True)
class BackupInfo:
    path: Path
    sha256: str
    integrity: str


def database_integrity(path: str | Path) -> str:
    db_path = Path(path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing_result"
    finally:
        connection.close()


def backup_database(source: str | Path, destination: str | Path) -> BackupInfo:
    source_path = Path(source)
    destination_path = Path(destination)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        raise FileExistsError(destination_path)
    source_connection = connect(source_path)
    destination_connection = sqlite3.connect(destination_path)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    integrity = database_integrity(destination_path)
    if integrity != "ok":
        destination_path.unlink(missing_ok=True)
        raise RuntimeError(f"backup falhou no integrity_check: {integrity}")
    digest = hashlib.sha256(destination_path.read_bytes()).hexdigest()
    return BackupInfo(destination_path, digest, integrity)


def restore_database(backup: str | Path, destination: str | Path) -> BackupInfo:
    backup_path = Path(backup)
    destination_path = Path(destination)
    if database_integrity(backup_path) != "ok":
        raise RuntimeError("backup de origem não passou no integrity_check")
    if destination_path.exists():
        raise FileExistsError(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, destination_path)
    integrity = database_integrity(destination_path)
    if integrity != "ok":
        destination_path.unlink(missing_ok=True)
        raise RuntimeError(f"restauração falhou no integrity_check: {integrity}")
    digest = hashlib.sha256(destination_path.read_bytes()).hexdigest()
    return BackupInfo(destination_path, digest, integrity)
