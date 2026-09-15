from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_agent_pr_pipeline_proof.py"
SPEC = importlib.util.spec_from_file_location("agent_pr_pipeline_proof", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_policy() -> dict:
    with (ROOT / "governance" / "agents" / "pr_pipeline_policy.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_policy_is_single_file_sandboxed_and_never_auto_merges() -> None:
    policy = load_policy()
    MODULE.validate_policy(policy)
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["proposal_path_prefix"] == "sandbox/agent-pr-proof/"
    assert policy["allowed_files_per_proposal"] == 1
    assert policy["direct_main_write_forbidden"] is True
    assert policy["operations_state_write_forbidden"] is True
    assert policy["auto_merge_forbidden"] is True
    assert policy["force_push_forbidden"] is True
    assert policy["required_workflow_dispatches"] == [
        "ci.yml",
        "agent-capability-proof.yml",
        "agent-resilience-proof.yml",
    ]


def test_plan_is_deterministic_and_confined_to_sandbox() -> None:
    policy = load_policy()
    sha = "a" * 40
    branch, path, payload = MODULE.build_proposal(sha, policy)
    assert branch == "agent-proof/aaaaaaaaaaaa"
    assert path == "sandbox/agent-pr-proof/aaaaaaaaaaaa.json"
    assert payload["source_main_sha"] == sha
    assert payload["effect"] == "EVIDENCE_ONLY_NO_PRODUCTION_EFFECT"
    assert payload["scientific_claim_level"] == "NONE"
    assert payload["requires_human_merge_review"] is True
    assert all(not path.startswith(prefix) for prefix in policy["forbidden_path_prefixes"])


def test_invalid_source_sha_is_rejected() -> None:
    with pytest.raises(ValueError):
        MODULE.build_proposal("not-a-sha", load_policy())


def test_policy_rejects_sensitive_scope_or_missing_guard() -> None:
    policy = load_policy()
    policy["proposal_path_prefix"] = "src/"
    with pytest.raises(ValueError):
        MODULE.validate_policy(policy)

    policy = load_policy()
    policy["auto_merge_forbidden"] = False
    with pytest.raises(ValueError):
        MODULE.validate_policy(policy)
