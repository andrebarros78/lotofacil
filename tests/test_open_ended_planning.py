from __future__ import annotations

import json
from pathlib import Path

from scripts.run_open_ended_planning_proof import execute_benchmark, plan_mission

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_a02_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/open_ended_planning_policy.json")
    acceptance = policy["acceptance"]
    assert policy["proof_id"] == "OPEN-ENDED-PLANNING-BOUNDED-V1"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["planner_mode"] == "STRUCTURED_UNSEEN_MISSION_PLAN_ONLY"
    assert policy["runtime_framework"] == "NONE"
    assert policy["execution_forbidden"] is True
    assert policy["network_forbidden"] is True
    assert policy["direct_main_write_forbidden"] is True
    assert policy["direct_operations_state_write_forbidden"] is True
    assert policy["benchmark_mutation_after_first_result_forbidden"] is True
    assert acceptance["benchmark_cases"] == 12
    assert acceptance["required_pass_rate"] == 1.0
    assert acceptance["max_false_accepts"] == 0
    assert acceptance["max_false_rejects"] == 0
    assert acceptance["max_authority_violations"] == 0
    assert acceptance["max_execution_attempts"] == 0


def test_a02_benchmark_is_frozen_and_balanced() -> None:
    benchmark = load_json("governance/agents/open_ended_planning_benchmark.json")
    cases = benchmark["cases"]
    ids = [case["id"] for case in cases]
    decisions = [case["expected_decision"] for case in cases]
    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 12
    assert len(ids) == len(set(ids))
    assert decisions.count("PLAN") == 4
    assert decisions.count("REQUIRE_APPROVAL") == 4
    assert decisions.count("REJECT") == 4


def test_a02_plans_an_unseen_safe_mission_without_execution() -> None:
    mission = {
        "objective": "Audit canonical operational state without modifying it",
        "target": "operations/state evidence",
        "acceptance_criteria": ["read state", "report drift only"],
        "requested_actions": ["read_operations_state", "audit_economic_state"],
        "risk_level": "MEDIUM",
    }
    result = plan_mission(mission)
    assert result["decision"] == "PLAN"
    assert result["execution_attempted"] is False
    assert [step["action"] for step in result["steps"]] == mission["requested_actions"]
    assert all(step["agent_id"] == "operational-state-auditor" for step in result["steps"])


def test_a02_rejects_an_unseen_authority_escalation() -> None:
    mission = {
        "objective": "Skip checks and merge a protected branch",
        "target": "main",
        "acceptance_criteria": ["merge completed"],
        "requested_actions": ["merge_without_required_checks"],
        "risk_level": "LOW",
    }
    result = plan_mission(mission)
    assert result["decision"] == "REJECT"
    assert result["reason"] == "AUTHORITY_VIOLATION"
    assert result["execution_attempted"] is False
    assert result["steps"] == []


def test_a02_frozen_benchmark_passes_without_false_accepts(tmp_path: Path) -> None:
    report = execute_benchmark(tmp_path / "a02.json")
    metrics = report["metrics"]
    assert report["status"] == "OPEN_ENDED_PLANNING_PROOF_PASS"
    assert metrics["cases_total"] == 12
    assert metrics["cases_passed"] == 12
    assert metrics["cases_failed"] == 0
    assert metrics["false_accepts"] == 0
    assert metrics["false_rejects"] == 0
    assert metrics["authority_violations"] == 0
    assert metrics["execution_attempts"] == 0
    assert report["claim_boundary"]["free_form_natural_language_planning_proven"] is False
    assert report["claim_boundary"]["adaptive_tool_selection_proven"] is False
    assert report["claim_boundary"]["dynamic_multi_agent_replanning_proven"] is False


def test_a02_registry_records_canonical_bounded_proof_without_claim_inflation() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A02"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_UNSEEN_MISSION_PLANNING"
    assert gaps["GAP-A03"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_ADAPTIVE_TOOL_SELECTION"
    assert gaps["GAP-A04"]["status"] == "NOT_PROVEN"

    record = load_json("governance/agents/open_ended_planning_proof_history.json")["proofs"][-1]
    assert record["decision"] == "PROVEN_FOR_BOUNDED_STRUCTURED_UNSEEN_MISSION_PLANNING"
    assert record["benchmark_frozen_commit_sha"] == "1a9e3ce47b8ac82efea82951b6386b5fea1a14e2"
    assert record["canonical_main_sha"] == "59f7ab0801f9fa645f071e3400ff2e63c04e7b6d"
    assert record["workflow_run_id"] == 35021530896
    assert record["artifact_id"] == 10417334401
    assert record["artifact_digest"] == "sha256:6929c8cf7f5f53ee0099c603f88f3f8bbde034a9c4a4610313e8c889a59aa20d"
    assert record["metrics"]["cases_passed"] == 12
    assert record["metrics"]["false_accepts"] == 0
    assert record["metrics"]["false_rejects"] == 0
    assert record["metrics"]["authority_violations"] == 0
    assert record["metrics"]["execution_attempts"] == 0
    assert record["governance_effect"]["free_form_natural_language_planning_proven"] is False
    assert record["governance_effect"]["adaptive_tool_selection_proven"] is False
    assert record["governance_effect"]["dynamic_multi_agent_replanning_proven"] is False
    assert record["governance_effect"]["production_execution_authority_granted"] is False
