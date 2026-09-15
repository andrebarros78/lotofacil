from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_agent_resilience_proof as resilience  # noqa: E402


def load_policy() -> dict:
    with (ROOT / "governance" / "agents" / "resilience_policy.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_resilience_policy_is_framework_independent_and_bounded() -> None:
    policy = load_policy()
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["runtime_framework"] == "NONE"
    assert policy["checkpoint"]["artifact_scope_only"] is True
    assert policy["checkpoint"]["payload_hash_required"] is True
    assert policy["retry"]["max_retries_per_mission"] == 1
    assert policy["retry"]["hidden_failure_forbidden"] is True
    assert policy["fault_injection"]["controlled_only"] is True
    assert policy["success_criteria"]["human_interventions"] == 0
    assert policy["success_criteria"]["runtime_framework_dependencies"] == 0
    assert policy["success_criteria"]["replay_fingerprint_must_match_clean_baseline"] is True


def test_resilience_definition_fingerprint_matches_capability_baseline() -> None:
    assert resilience.definition_fingerprint() == "74c33e83f6018796075d1d86ec93725c7aff30ea8538d2350fb5a1c47fb95702"
    assert resilience.CLEAN_REPLAY_FINGERPRINT == "603b9444be2982a60840530e092f379e61f775958592443705654994b2db87cd"


def test_checkpoint_payload_hash_detects_mutation() -> None:
    payload = {
        "schema_version": 1,
        "definition_fingerprint_sha256": resilience.definition_fingerprint(),
        "next_index": 0,
        "results": [],
        "checkpoint_resumes": 0,
        "injected_interruptions": 0,
        "transient_failures_injected": 0,
        "transient_failures_recovered": 0,
    }
    payload["checkpoint_payload_sha256"] = resilience.checkpoint_hash(payload)
    assert payload["checkpoint_payload_sha256"] == resilience.checkpoint_hash(payload)
    payload["next_index"] = 1
    assert payload["checkpoint_payload_sha256"] != resilience.checkpoint_hash(payload)


def test_resilience_paths_cannot_escape_artifact_scope() -> None:
    with pytest.raises(ValueError):
        resilience.artifact_path("outside-proof.json")
    allowed = resilience.artifact_path("artifacts/test-resilience.json")
    assert allowed.parent == (ROOT / "artifacts").resolve()
