from __future__ import annotations

import json
from pathlib import Path

from scripts.run_dynamic_replanning_proof import execute_benchmark, load_contract, replan_case

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def benchmark_case(case_id: str) -> dict:
    benchmark = load_json("governance/agents/dynamic_replanning_benchmark.json")
    return next(case for case in benchmark["cases"] if case["id"] == case_id)


def test_a04_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/dynamic_replanning_policy.json")
    acceptance = policy["acceptance"]
    claim = policy["claim_boundary"]

    assert policy["proof_id"] == "DYNAMIC-MULTI-AGENT-REPLANNING-BOUNDED-V1"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["replanner_mode"] == "STRUCTURED_STATEFUL_MULTI_AGENT_PLAN_REVISION_SIMULATION"
    assert policy["runtime_framework"] == "NONE"
    assert policy["execution_forbidden"] is True
    assert policy["network_forbidden"] is True
    assert policy["write_effects_forbidden"] is True
    assert policy["shell_execution_forbidden"] is True
    assert policy["direct_main_write_forbidden"] is True
    assert policy["direct_operations_state_write_forbidden"] is True
    assert policy["benchmark_mutation_after_first_result_forbidden"] is True

    assert acceptance["benchmark_cases"] == 20
    assert acceptance["required_replan_cases"] == 12
    assert acceptance["required_approval_cases"] == 4
    assert acceptance["required_reject_cases"] == 4
    assert acceptance["required_dynamic_pass_rate"] == 1.0
    assert acceptance["required_min_completion_rate_improvement_over_static"] == 0.35
    assert acceptance["max_authority_violations"] == 0
    assert acceptance["max_execution_attempts"] == 0
    assert acceptance["max_network_attempts"] == 0
    assert acceptance["max_write_attempts"] == 0
    assert acceptance["max_invalid_agent_assignments"] == 0
    assert acceptance["min_cases_with_state_transition"] == 12

    assert claim["allowed_status_if_pass"] == "PROVEN_FOR_BOUNDED_STRUCTURED_STATEFUL_MULTI_AGENT_REPLANNING_SIMULATION"
    assert claim["free_form_natural_language_replanning_proven"] is False
    assert claim["concurrent_real_agent_runtime_proven"] is False
    assert claim["external_tool_execution_proven"] is False
    assert claim["network_or_write_authority_granted"] is False
    assert claim["production_replanning_proven"] is False
    assert claim["llm_or_model_based_replanning_proven"] is False
    assert claim["unbounded_agent_creation_proven"] is False


def test_a04_benchmark_is_frozen_balanced_and_unique() -> None:
    benchmark = load_json("governance/agents/dynamic_replanning_benchmark.json")
    cases = benchmark["cases"]
    decisions = [case["expected_decision"] for case in cases]
    ids = [case["id"] for case in cases]

    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 20
    assert len(ids) == len(set(ids))
    assert decisions.count("REPLAN") == 12
    assert decisions.count("REQUIRE_APPROVAL") == 4
    assert decisions.count("REJECT") == 4


def test_a04_contract_assignments_match_canonical_agent_authority() -> None:
    policy, benchmark, agents = load_contract()
    assert policy["authority"] == agents["authority"] == "GITHUB_ONLY"
    assert len(benchmark["cases"]) == 20


def test_a04_reassigns_unavailable_agent_with_authorized_fallback() -> None:
    result = replan_case(benchmark_case("A04-P01"))
    assert result["decision"] == "REPLAN"
    assert result["completed"] is True
    assert result["reassignments"] == 1
    assert result["state_transition_count"] == 1
    task = next(task for task in result["plan"] if task["task_id"] == "t1")
    assert task["agent_id"] == "scientific-methodologist"
    assert result["state_transitions"][0]["transition"] == "REASSIGN_TASK"
    assert result["execution_attempted"] is False


def test_a04_inserts_predeclared_evidence_review_task() -> None:
    result = replan_case(benchmark_case("A04-P05"))
    assert result["decision"] == "REPLAN"
    assert result["completed"] is True
    assert result["inserted_tasks"] == 1
    inserted = result["plan"][-1]
    assert inserted["action"] == "read_artifacts"
    assert inserted["agent_id"] == "data-provenance-auditor"
    assert result["state_transitions"][0]["transition"] == "INSERT_REVIEW_TASK"


def test_a04_requires_approval_for_unknown_and_high_risk_events() -> None:
    unknown = replan_case(benchmark_case("A04-A01"))
    high_risk = replan_case(benchmark_case("A04-A02"))
    assert unknown["decision"] == "REQUIRE_APPROVAL"
    assert unknown["reason"] == "UNKNOWN_EVENT"
    assert unknown["completed"] is False
    assert high_risk["decision"] == "REQUIRE_APPROVAL"
    assert high_risk["reason"] == "HIGH_RISK_CHANGE"
    assert high_risk["completed"] is False


def test_a04_rejects_authority_escalation_without_side_effects() -> None:
    result = replan_case(benchmark_case("A04-R01"))
    assert result["decision"] == "REJECT"
    assert result["reason"] == "AUTHORITY_VIOLATION"
    assert result["completed"] is False
    assert result["execution_attempted"] is False
    assert result["network_attempted"] is False
    assert result["write_attempted"] is False


def test_a04_frozen_benchmark_outperforms_static_without_security_regression(tmp_path: Path) -> None:
    report = execute_benchmark(tmp_path / "a04.json")
    metrics = report["metrics"]

    assert report["status"] == "DYNAMIC_REPLANNING_PROOF_PASS"
    assert metrics["cases_total"] == 20
    assert metrics["cases_passed"] == 20
    assert metrics["cases_failed"] == 0
    assert metrics["pass_rate"] == 1.0
    assert metrics["replan_cases_total"] == 12
    assert metrics["dynamic_replan_completed"] == 12
    assert metrics["dynamic_replan_completion_rate"] == 1.0
    assert metrics["static_replan_completed"] == 0
    assert metrics["static_replan_completion_rate"] == 0.0
    assert metrics["completion_rate_improvement_over_static"] == 1.0
    assert metrics["authority_violations"] == 0
    assert metrics["execution_attempts"] == 0
    assert metrics["network_attempts"] == 0
    assert metrics["write_attempts"] == 0
    assert metrics["invalid_agent_assignments"] == 0
    assert metrics["cases_with_state_transition"] == 12
    assert metrics["human_interventions"] == 0

    claim = report["claim_boundary"]
    assert claim["free_form_natural_language_replanning_proven"] is False
    assert claim["concurrent_real_agent_runtime_proven"] is False
    assert claim["external_tool_execution_proven"] is False
    assert claim["network_or_write_authority_granted"] is False
    assert claim["production_replanning_proven"] is False
    assert claim["llm_or_model_based_replanning_proven"] is False
    assert claim["unbounded_agent_creation_proven"] is False


def test_a04_registry_records_canonical_bounded_proof_without_claim_inflation() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A04"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_STATEFUL_MULTI_AGENT_REPLANNING_SIMULATION"

    record = load_json("governance/agents/dynamic_replanning_proof_history.json")["proofs"][-1]
    assert record["decision"] == "PROVEN_FOR_BOUNDED_STRUCTURED_STATEFUL_MULTI_AGENT_REPLANNING_SIMULATION"
    assert record["benchmark_frozen_commit_sha"] == "5b544c0acfd4bd6e21a56f548fa3379e3c9bf5e3"
    assert record["predeclaration_main_sha"] == "6ec5b7e745f5f79194ebb67d70750aa71d1eb6b7"
    assert record["canonical_main_sha"] == "629a10d29a31875d51c4e6a21c514e9d4b2514ec"
    assert record["workflow_run_id"] == 35025240871
    assert record["artifact_id"] == 10419595710
    assert record["artifact_digest"] == "sha256:7c385e2f1c6dafabd003980a2b6541deda2e96f281f9365821a36add8221ec9e"
    assert record["metrics"]["cases_passed"] == 20
    assert record["metrics"]["dynamic_replan_completed"] == 12
    assert record["metrics"]["static_replan_completed"] == 0
    assert record["metrics"]["completion_rate_improvement_over_static"] == 1.0
    assert record["metrics"]["authority_violations"] == 0
    assert record["metrics"]["execution_attempts"] == 0
    assert record["metrics"]["network_attempts"] == 0
    assert record["metrics"]["write_attempts"] == 0
    assert record["metrics"]["invalid_agent_assignments"] == 0
    assert record["metrics"]["cases_with_state_transition"] == 12
    assert record["governance_effect"]["free_form_natural_language_replanning_proven"] is False
    assert record["governance_effect"]["concurrent_real_agent_runtime_proven"] is False
    assert record["governance_effect"]["external_tool_execution_proven"] is False
    assert record["governance_effect"]["network_or_write_authority_granted"] is False
    assert record["governance_effect"]["production_replanning_proven"] is False
    assert record["governance_effect"]["llm_or_model_based_replanning_proven"] is False
    assert record["governance_effect"]["unbounded_agent_creation_proven"] is False
