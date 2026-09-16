from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validate_post_merge_proof_confirmations import validate

ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path("governance/agents/post_merge_proof_confirmations.json")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def copy_governance(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(ROOT / "governance" / "agents", target / "governance" / "agents")
    return target


def test_post_merge_proof_confirmation_validator_passes() -> None:
    result = validate(ROOT)
    assert result == {
        "status": "POST_MERGE_PROOF_CONFIRMATIONS_PASS",
        "authority": "GITHUB_ONLY",
        "confirmations": 1,
        "gaps_linked": 1,
    }


def test_post_merge_confirmation_rejects_registry_status_drift(tmp_path: Path) -> None:
    root = copy_governance(tmp_path)
    ledger_path = root / LEDGER_REL
    ledger = load_json(ledger_path)
    ledger["confirmations"][0]["registry_status"] = "PROVEN_FOR_SOMETHING_ELSE"
    save_json(ledger_path, ledger)

    with pytest.raises(AssertionError, match="registry status mismatch"):
        validate(root)


def test_post_merge_confirmation_rejects_unknown_proof_id(tmp_path: Path) -> None:
    root = copy_governance(tmp_path)
    ledger_path = root / LEDGER_REL
    ledger = load_json(ledger_path)
    ledger["confirmations"][0]["proof_id"] = "MISSING-PROOF"
    save_json(ledger_path, ledger)

    with pytest.raises(AssertionError, match="proof id not found"):
        validate(root)


def test_post_merge_confirmation_rejects_claim_expansion(tmp_path: Path) -> None:
    root = copy_governance(tmp_path)
    ledger_path = root / LEDGER_REL
    ledger = load_json(ledger_path)
    ledger["confirmations"][0]["governance_effect"]["claim_expanded"] = True
    save_json(ledger_path, ledger)

    with pytest.raises(AssertionError, match="claim expansion forbidden"):
        validate(root)


def test_post_merge_confirmation_rejects_malformed_artifact_digest(tmp_path: Path) -> None:
    root = copy_governance(tmp_path)
    ledger_path = root / LEDGER_REL
    ledger = load_json(ledger_path)
    ledger["confirmations"][0]["post_merge_confirmation"]["artifact_digest"] = "sha256:not-a-digest"
    save_json(ledger_path, ledger)

    with pytest.raises(AssertionError, match="invalid post-merge artifact digest"):
        validate(root)
