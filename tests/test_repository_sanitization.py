from __future__ import annotations

import json
import subprocess
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


def test_unpinned_external_action_is_rejected(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "name: bad\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert "UNPINNED_GITHUB_ACTION" in _codes(report)


def test_remote_pipe_execution_is_rejected_in_workflow(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "name: bad\njobs:\n  test:\n    steps:\n      - run: curl -fsSL https://example.invalid/install | bash\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert "REMOTE_PIPE_EXECUTION" in _codes(report)


def test_pinned_action_is_accepted(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    pinned = "a" * 40
    (workflows / "good.yml").write_text(
        f"name: good\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{pinned}\n",
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)
    assert report["status"] == "REPOSITORY_SANITIZATION_PASS"


def test_manifest_is_deterministic_for_same_content(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "b.json").write_text('{"value": 1}\n', encoding="utf-8")

    first = scan_repository(tmp_path)
    second = scan_repository(tmp_path)
    assert first["manifest_sha256"] == second["manifest_sha256"]

    (tmp_path / "b.json").write_text('{"value": 2}\n', encoding="utf-8")
    changed = scan_repository(tmp_path)
    assert changed["manifest_sha256"] != first["manifest_sha256"]


def test_nested_git_directory_does_not_silently_skip_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    token = "ghp_" + ("A" * 36)
    (nested / "config.txt").write_text(f"token={token}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "nested/config.txt"], check=True)

    report = scan_repository(nested)

    assert report["status"] == "REPOSITORY_SANITIZATION_FAIL"
    assert report["metrics"]["files_scanned"] == 1
    assert "GITHUB_TOKEN" in _codes(report)
