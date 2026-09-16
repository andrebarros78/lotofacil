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
    with (ROOT / "governance" / "agents" / "resilience_policy.json").open(
        "r", encoding="utf-8"
    ) as handle:
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
    assert (
        policy["success_criteria"]["replay_fingerprint_must_match_clean_baseline"]
        is True
    )


def test_resilience_fingerprints_follow_current_integrated_baseline() -> None:
    definition = resilience.definition_fingerprint()
    replay = resilience.clean_replay_fingerprint()

    assert len(definition) == 64
    assert len(replay) == 64
    assert resilience.CLEAN_REPLAY_FINGERPRINT == replay

    missions_doc, tools_doc, agents_doc, skills_doc = resilience.load_contract()
    assert definition == resilience.stable_hash(
        {
            "agents": agents_doc["agents"],
            "skills": skills_doc["skills"],
            "missions": missions_doc["missions"],
            "tools": tools_doc["tools"],
        }
    )

    expected_replay = [
        {
            "mission_id": mission["id"],
            "agent_id": mission["agent_id"],
            "required_skills": mission["required_skills"],
            "tool_id": mission["tool_id"],
            "returncode": 0,
            "status": "PASS",
        }
        for mission in missions_doc["missions"]
    ]
    assert replay == resilience.stable_hash(expected_replay)


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
