from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_merge_gates import verify  # noqa: E402


def _fixture_root(tmp_path: Path) -> Path:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "governance").mkdir(parents=True)
    shutil.copy2(ROOT / ".github" / "workflows" / "merge-gates.yml", tmp_path / ".github" / "workflows" / "merge-gates.yml")
    shutil.copy2(ROOT / "governance" / "merge-gates.json", tmp_path / "governance" / "merge-gates.json")
    return tmp_path


def test_canonical_merge_gate_contract_passes() -> None:
    report = verify(ROOT)
    assert report["status"] == "MERGE_GATES_CONTRACT_PASS", json.dumps(report, indent=2)
    assert report["violations"] == []
    assert report["required_status_checks"] == [
        "CI",
        "Scientific Gate",
        "Operational Integrity Gate",
        "Security/Sanitization Gate",
        "Release Candidate Gate",
    ]


def test_missing_scientific_gate_fails_closed(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    workflow = root / ".github" / "workflows" / "merge-gates.yml"
    text = workflow.read_text(encoding="utf-8").replace("name: Scientific Gate", "name: Scientific Gate RENAMED")
    workflow.write_text(text, encoding="utf-8")
    report = verify(root)
    assert report["status"] == "MERGE_GATES_CONTRACT_FAIL"
    assert "MISSING_STABLE_CHECK:Scientific Gate" in report["violations"]


def test_release_candidate_dependency_removal_fails_closed(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    workflow = root / ".github" / "workflows" / "merge-gates.yml"
    text = workflow.read_text(encoding="utf-8").replace(
        "needs: [ci, scientific, operational, security]",
        "needs: [ci, scientific, operational]",
    )
    workflow.write_text(text, encoding="utf-8")
    report = verify(root)
    assert report["status"] == "MERGE_GATES_CONTRACT_FAIL"
    assert "RELEASE_CANDIDATE_DEPENDENCIES_MISMATCH" in report["violations"]
