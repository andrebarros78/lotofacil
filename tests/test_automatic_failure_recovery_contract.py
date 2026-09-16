from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_a07_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/automatic_failure_recovery_policy.json")
    assert policy["proof_id"] == "AUTOMATIC-FAILURE-RECOVERY-BOUNDED-V1"
    assert policy["gap_id"] == "GAP-A07"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["runtime_framework"] == "NONE"
    assert policy["execution_scope"] == "CONTROLLED_STRUCTURED_SIMULATION_ONLY"
    guard = policy["policy"]
    assert guard["automatic_recovery_required"] is True
    assert guard["human_intervention_forbidden"] is True
    assert guard["hidden_failure_forbidden"] is True
    assert guard["authority_escalation_forbidden"] is True
    assert guard["arbitrary_network_target_forbidden"] is True
    assert guard["provider_write_requests_forbidden"] is True
    assert guard["shell_execution_forbidden"] is True
    assert guard["credential_material_forbidden"] is True
    assert guard["max_recovery_actions_per_case"] == 1
    assert guard["max_total_attempts_per_case"] == 2
    acceptance = policy["acceptance"]
    assert acceptance["benchmark_cases"] == 24
    assert acceptance["required_pass_rate"] == 1.0
    assert acceptance["max_false_recoveries"] == 0
    assert acceptance["max_false_blocks"] == 0
    assert acceptance["max_authority_violations"] == 0
    assert acceptance["max_write_attempts"] == 0
    assert acceptance["max_shell_attempts"] == 0
    assert acceptance["max_credential_exposures"] == 0
    claims = policy["claim_boundary"]
    assert claims["allowed_status_if_pass"] == "PROVEN_FOR_BOUNDED_STRUCTURED_AUTOMATIC_FAILURE_RECOVERY"
    assert claims["real_world_arbitrary_network_recovery_proven"] is False
    assert claims["real_credential_refresh_proven"] is False
    assert claims["arbitrary_dependency_discovery_proven"] is False
    assert claims["free_form_dynamic_replanning_proven"] is False
    assert claims["production_mutation_authority_granted"] is False
    assert claims["general_failure_recovery_proven"] is False


def test_a07_benchmark_is_frozen_unique_and_covers_required_classes() -> None:
    benchmark = load_json("governance/agents/automatic_failure_recovery_benchmark.json")
    cases = benchmark["cases"]
    ids = [case["id"] for case in cases]
    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 24
    assert len(ids) == len(set(ids))
    assert ids == [f"A07-{index:02d}" for index in range(1, 25)]
    classes = {case["failure_class"] for case in cases}
    assert {
        "NETWORK_TRANSIENT",
        "NETWORK_PERSISTENT",
        "AUTHORIZATION_EXPIRED_REFRESHABLE",
        "AUTHORIZATION_FORBIDDEN",
        "DEPENDENCY_UNAVAILABLE_WITH_FALLBACK",
        "DEPENDENCY_UNAVAILABLE_NO_FALLBACK",
        "REPLANNABLE_STEP_FAILURE",
        "NON_REPLANNABLE_STEP_FAILURE",
        "UNKNOWN_FAILURE",
    } <= classes
    assert any(case.get("requests_write") for case in cases)
    assert any(case.get("requests_credential_material") for case in cases)


def test_a07_registry_remains_partial_before_confirmatory_main_evidence() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A07"]["status"] == "PARTIALLY_PROVEN_BOUNDED_TRANSIENT_RETRY_ONLY"
