from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_capability_plan_is_executable_and_bounded() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_agent_capability_proof.py", "--plan"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "AGENT_CAPABILITY_PLAN_VALID"
    assert payload["contract"]["missions"] == 8
    assert payload["contract"]["tools"] == 8
    assert payload["contract"]["runtime_framework"] == "NONE"
    assert len(payload["plan"]) == 8
    assert all(item["risk_level"] == "LOW" for item in payload["plan"])
    assert all(item["command"][0] == sys.executable for item in payload["plan"])


def test_capability_registry_is_read_only_and_framework_independent() -> None:
    doc = load_json("governance/agents/capability_missions.json")
    policy = doc["mission_policy"]
    assert doc["authority"] == "GITHUB_ONLY"
    assert doc["runtime_framework"] == "NONE"
    assert policy["read_only_only"] is True
    assert policy["shell_execution_forbidden"] is True
    assert policy["direct_main_write_forbidden"] is True
    assert policy["direct_operations_state_write_forbidden"] is True


def test_tool_bindings_have_no_generic_shell_or_external_runtime() -> None:
    doc = load_json("governance/agents/tool_bindings.json")
    assert doc["policy"]["python_executable_only"] is True
    assert doc["policy"]["shell_false_required"] is True
    assert doc["policy"]["write_effects_forbidden"] is True
    assert doc["policy"]["network_required"] is False
    assert {tool["kind"] for tool in doc["tools"]} <= {"script", "pytest"}


def test_every_capability_mission_has_a_known_agent_and_tool() -> None:
    agents = {agent["id"] for agent in load_json("governance/agents/agents.json")["agents"]}
    tools = {tool["id"] for tool in load_json("governance/agents/tool_bindings.json")["tools"]}
    missions = load_json("governance/agents/capability_missions.json")["missions"]
    assert len(missions) == 8
    for mission in missions:
        assert mission["agent_id"] in agents
        assert mission["tool_id"] in tools
        assert mission["acceptance"] == "exit_code_zero"


def test_capability_gaps_preserve_bounded_scope_and_unproven_frontiers() -> None:
    doc = load_json("governance/agents/capability_gaps.json")
    gaps = {gap["capability"]: gap for gap in doc["gaps"]}
    assert doc["baseline_type"] == "BOUNDED_DETERMINISTIC_AUTONOMY"
    assert gaps["bounded_predeclared_mission_execution"]["status"] == "IMPLEMENTED_CONTINUOUS_PROOF_REQUIRED"
    assert gaps["durable_agent_checkpoint_resume"]["status"] == "PROVEN_FOR_BOUNDED_PREDECLARED_MISSIONS_CONTINUOUS_PROOF_REQUIRED"
    assert gaps["external_mcp_tool_execution"]["status"] == "PARTIALLY_PROVEN_ISOLATED_STATELESS_ADAPTER_ONLY"
    assert gaps["automatic_failure_recovery"]["status"] == "PARTIALLY_PROVEN_BOUNDED_TRANSIENT_RETRY_ONLY"
    assert gaps["semantic_handoff_quality_evaluation"]["status"] == "PARTIALLY_PROVEN_STRUCTURED_HANDOFF_EVALUATION_ONLY"
    assert gaps["agent_proposed_code_change_to_pr_pipeline"]["status"] == "PARTIALLY_PROVEN_BRANCH_COMMIT_CHECKS_PR_CREATION_BLOCKED_BY_REPO_POLICY"
    for capability in (
        "open_ended_mission_planning",
        "adaptive_tool_selection",
        "dynamic_multi_agent_replanning",
    ):
        assert gaps[capability]["status"] == "NOT_PROVEN"
    assert gaps["agent_runtime_framework_value"]["status"] == "NOT_ESTABLISHED"


def test_a09_history_preserves_external_blocker_without_authority_escalation() -> None:
    record = load_json("governance/agents/pr_pipeline_proof_history.json")["proofs"][0]
    assert record["decision"] == "PARTIALLY_PROVEN_EXTERNAL_REPOSITORY_POLICY_BLOCKER"
    assert record["proposal_scope"]["files_changed"] == 1
    assert record["proposal_scope"]["production_effect"] is False
    assert all(item["conclusion"] == "success" for item in record["required_workflows"])
    assert record["pipeline_metrics"]["human_interventions"] == 0
    assert record["pipeline_metrics"]["direct_main_writes"] == 0
    assert record["pipeline_metrics"]["operations_state_writes"] == 0
    assert record["pipeline_metrics"]["auto_merge_attempts"] == 0
    assert record["pull_request_created"] is False
    assert record["blocker"]["http_status"] == 403
    assert record["governance_effect"]["general_code_write_authority_granted"] is False
