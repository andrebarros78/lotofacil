from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.prove_disaster_recovery import (
    parse_sha256sums,
    validate_manifest,
    verify_checksums,
)


GATES = (
    "CI",
    "Scientific Gate",
    "Operational Integrity Gate",
    "Security/Sanitization Gate",
    "Release Candidate Gate",
)


def test_sha256sums_rejects_duplicate_names(tmp_path: Path) -> None:
    p = tmp_path / "SHA256SUMS.txt"
    p.write_text(("a" * 64) + "  file.bin\n" + ("b" * 64) + "  file.bin\n", encoding="ascii")
    with pytest.raises(RuntimeError, match="DR_DUPLICATE_SHA256SUMS_NAME"):
        parse_sha256sums(p)


def test_release_asset_tampering_is_detected(tmp_path: Path) -> None:
    payload = tmp_path / "asset.bin"
    payload.write_bytes(b"before")
    sums = {"asset.bin": hashlib.sha256(b"before").hexdigest()}
    payload.write_bytes(b"after")
    with pytest.raises(RuntimeError, match="DR_RELEASE_ASSET_HASH_MISMATCH"):
        verify_checksums(tmp_path, sums)


def test_manifest_requires_same_release_and_state_shas() -> None:
    manifest = {
        "schema_version": "r4-release-manifest-v1",
        "canonical_sha": "release-sha",
        "operations_state_sha": "state-sha",
        "gate_results": {name: "success" for name in GATES},
        "release_proof": "success",
        "predictive_evidence": "NOT_ESTABLISHED",
    }
    validate_manifest(
        manifest,
        code_sha="release-sha",
        state_sha="state-sha",
        expected_release_sha="release-sha",
    )
    with pytest.raises(RuntimeError, match="DR_OPERATIONAL_STATE_SHA_MISMATCH"):
        validate_manifest(
            manifest,
            code_sha="release-sha",
            state_sha="different-state",
            expected_release_sha="release-sha",
        )


def test_manifest_fails_closed_on_failed_required_gate() -> None:
    gates = {name: "success" for name in GATES}
    gates["Scientific Gate"] = "failure"
    manifest = {
        "schema_version": "r4-release-manifest-v1",
        "canonical_sha": "release-sha",
        "operations_state_sha": "state-sha",
        "gate_results": gates,
        "release_proof": "success",
        "predictive_evidence": "NOT_ESTABLISHED",
    }
    with pytest.raises(RuntimeError, match="DR_REQUIRED_GATE_NOT_SUCCESS:Scientific Gate"):
        validate_manifest(
            manifest,
            code_sha="release-sha",
            state_sha="state-sha",
            expected_release_sha="release-sha",
        )
