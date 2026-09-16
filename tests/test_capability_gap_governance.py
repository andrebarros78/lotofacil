from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validate_agent_ecosystem import (
    PROOF_HISTORY_BY_GAP,
    validate_capability_gap_governance,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_AGENTS_DIR = ROOT / "governance" / "agents"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def copy_gap_governance(tmp_path: Path) -> tuple[Path, Path]:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    gaps_path = agents_dir / "capability_gaps.json"
    shutil.copy2(SOURCE_AGENTS_DIR / "capability_gaps.json", gaps_path)
    for history_name in PROOF_HISTORY_BY_GAP.values():
        shutil.copy2(SOURCE_AGENTS_DIR / history_name, agents_dir / history_name)
    return gaps_path, agents_dir


def test_current_capability_gap_governance_is_consistent() -> None:
    result = validate_capability_gap_governance()
    assert result == {
        "capability_gaps": 10,
        "dedicated_proof_histories": 8,
        "continuous_proof_gaps": 2,
    }


def test_capability_gap_governance_rejects_registry_status_drift(tmp_path: Path) -> None:
    gaps_path, agents_dir = copy_gap_governance(tmp_path)
    gaps_doc = load_json(gaps_path)
    for gap in gaps_doc["gaps"]:
        if gap["id"] == "GAP-A02":
            gap["status"] = "DRIFTED_STATUS"
            break
    write_json(gaps_path, gaps_doc)

    with pytest.raises(AssertionError, match="proof decision/status drift for GAP-A02"):
        validate_capability_gap_governance(gaps_path, agents_dir)


def test_capability_gap_governance_rejects_missing_history(tmp_path: Path) -> None:
    gaps_path, agents_dir = copy_gap_governance(tmp_path)
    history_name = PROOF_HISTORY_BY_GAP["GAP-A07"]
    (agents_dir / history_name).unlink()

    with pytest.raises(AssertionError, match="missing proof history for GAP-A07"):
        validate_capability_gap_governance(gaps_path, agents_dir)


def test_capability_gap_governance_rejects_wrong_gap_reference(tmp_path: Path) -> None:
    gaps_path, agents_dir = copy_gap_governance(tmp_path)
    history_path = agents_dir / PROOF_HISTORY_BY_GAP["GAP-A03"]
    history_doc = load_json(history_path)
    history_doc["proofs"][-1]["gap_id"] = "GAP-A99"
    write_json(history_path, history_doc)

    with pytest.raises(AssertionError, match="references wrong gap for GAP-A03"):
        validate_capability_gap_governance(gaps_path, agents_dir)


def test_capability_gap_governance_rejects_orphan_history(tmp_path: Path) -> None:
    gaps_path, agents_dir = copy_gap_governance(tmp_path)
    source = agents_dir / PROOF_HISTORY_BY_GAP["GAP-A02"]
    shutil.copy2(source, agents_dir / "orphan_proof_history.json")

    with pytest.raises(AssertionError, match="proof history inventory drift"):
        validate_capability_gap_governance(gaps_path, agents_dir)
