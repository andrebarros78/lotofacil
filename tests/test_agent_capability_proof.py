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
    assert gaps["open_ended_mission_planning"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_UNSEEN_MISSION_PLANNING"
    assert gaps["adaptive_tool_selection"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_ADAPTIVE_TOOL_SELECTION"
    assert gaps["dynamic_multi_agent_replanning"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_STATEFUL_MULTI_AGENT_REPLANNING_SIMULATION"
    assert gaps["durable_agent_checkpoint_resume"]["status"] == "PROVEN_FOR_BOUNDED_PREDECLARED_MISSIONS_CONTINUOUS_PROOF_REQUIRED"
    assert gaps["external_mcp_tool_execution"]["status"] == "PROVEN_FOR_BOUNDED_AUTHENTICATED_EXTERNAL_MCP_READ_ONLY_GITHUB_PROVIDER"
    assert gaps["automatic_failure_recovery"]["status"] == "PARTIALLY_PROVEN_BOUNDED_TRANSIENT_RETRY_ONLY"
    assert gaps["semantic_handoff_quality_evaluation"]["status"] == "PARTIALLY_PROVEN_STRUCTURED_HANDOFF_EVALUATION_ONLY"
    assert gaps["agent_proposed_code_change_to_pr_pipeline"]["status"] == "PROVEN_FOR_BOUNDED_SANDBOX_PROPOSAL_TO_PR_WITH_HUMAN_MERGE_REQUIRED"
    assert gaps["agent_runtime_framework_value"]["status"] == "NOT_ESTABLISHED"


def test_a09_history_records_blocker_then_bounded_proof_without_authority_escalation() -> None:
    proofs = load_json("governance/agents/pr_pipeline_proof_history.json")["proofs"]
    blocked = proofs[0]
    proven = proofs[-1]

    assert blocked["decision"] == "PARTIALLY_PROVEN_EXTERNAL_REPOSITORY_POLICY_BLOCKER"
    assert blocked["pull_request_created"] is False
    assert blocked["blocker"]["http_status"] == 403

    assert proven["decision"] == "PROVEN_FOR_BOUNDED_SANDBOX_PROPOSAL_TO_PR_WITH_HUMAN_MERGE_REQUIRED"
    assert proven["proposal_scope"]["files_changed"] == 1
    assert proven["proposal_scope"]["production_effect"] is False
    assert all(item["conclusion"] == "success" for item in proven["required_workflows"])
    assert proven["pipeline_metrics"]["human_interventions"] == 0
    assert proven["pipeline_metrics"]["direct_main_writes"] == 0
    assert proven["pipeline_metrics"]["operations_state_writes"] == 0
    assert proven["pipeline_metrics"]["auto_merge_attempts"] == 0
    assert proven["pull_request_created"] is True
    assert proven["pull_request_number"] == 38
    assert proven["pull_request_state"] == "open"
    assert proven["pull_request_merged"] is False
    assert proven["evidence"]["workflow_run_id"] == 35019415725
    assert proven["evidence"]["artifact_id"] == 10416941486
    assert proven["governance_effect"]["general_code_write_authority_granted"] is False
    assert proven["governance_effect"]["auto_merge_authority_granted"] is False
    assert proven["governance_effect"]["operations_state_authority_granted"] is False
