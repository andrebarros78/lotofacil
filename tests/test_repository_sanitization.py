from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sanitize_repository import scan_repository  # noqa: E402


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["violations"]}


def test_current_repository_is_sanitized() -> None:
    report = scan_repository(ROOT)
    assert report["status"] == "REPOSITORY_SANITIZATION_PASS", json.dumps(
        report["violations"], indent=2, sort_keys=True
    )
    assert report["metrics"]["violations"] == 0
    assert report["metrics"]["files_scanned"] > 0
    assert len(report["manifest_sha256"]) == 64


def test_env_and_runtime_artifact_paths_are_rejected(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SAFE_PLACEHOLDER=1\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "proof.json").write_text("{}\n", encoding="utf-8")

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert "SENSITIVE_OR_RUNTIME_FILE" in _codes(report)
    assert "GENERATED_OR_RUNTIME_PATH" in _codes(report)


def test_high_confidence_token_material_is_rejected(tmp_path: Path) -> None:
    token = "ghp_" + ("A" * 36)
    (tmp_path / "config.txt").write_text(f"token={token}\n", encoding="utf-8")

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert "GITHUB_TOKEN" in _codes(report)


def test_private_key_material_is_rejected(tmp_path: Path) -> None:
    marker = "-----BEGIN " + "PRIVATE KEY-----"
    (tmp_path / "notes.txt").write_text(marker + "\n", encoding="utf-8")

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert "PRIVATE_KEY_MATERIAL" in _codes(report)


def test_placeholder_credentials_are_not_false_positives(tmp_path: Path) -> None:
    (tmp_path / "example.txt").write_text(
        'client_secret="example-placeholder-value"\n', encoding="utf-8"
    )

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_PASS"
    assert report["metrics"]["violations"] == 0


def test_manifest_is_deterministic_for_same_content(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "b.json").write_text('{"value": 1}\n', encoding="utf-8")

    first = scan_repository(tmp_path)
    second = scan_repository(tmp_path)
    assert first["manifest_sha256"] == second["manifest_sha256"]

    (tmp_path / "b.json").write_text('{"value": 2}\n', encoding="utf-8")
    changed = scan_repository(tmp_path)
    assert changed["manifest_sha256"] != first["manifest_sha256"]
