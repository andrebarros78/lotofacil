from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_automatic_failure_recovery_proof as recovery  # noqa: E402


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def case_by_id(case_id: str) -> dict:
    cases = load_json("governance/agents/automatic_failure_recovery_benchmark.json")["cases"]
    return copy.deepcopy(next(case for case in cases if case["id"] == case_id))


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


def test_a07_full_frozen_benchmark_passes_without_effects() -> None:
    report = recovery.run_benchmark()
    metrics = report["metrics"]
    assert report["status"] == "AUTOMATIC_FAILURE_RECOVERY_PROOF_PASS"
    assert metrics["cases_total"] == 24
    assert metrics["cases_passed"] == 24
    assert metrics["cases_failed"] == 0
    assert metrics["pass_rate"] == 1.0
    assert metrics["false_recoveries"] == 0
    assert metrics["false_blocks"] == 0
    assert metrics["action_mismatches"] == 0
    assert metrics["authority_violations"] == 0
    assert metrics["network_target_violations"] == 0
    assert metrics["write_attempts"] == 0
    assert metrics["shell_attempts"] == 0
    assert metrics["credential_exposures"] == 0
    assert metrics["human_interventions"] == 0
    assert metrics["actual_external_network_calls"] == 0
    assert metrics["audited_cases"] == 24
    assert all(result["recovery_actions"] <= 1 for result in report["case_results"])
    assert all(result["attempts"] <= 2 for result in report["case_results"])


def test_a07_engine_uses_structured_state_not_case_id_answer_lookup() -> None:
    case = case_by_id("A07-01")
    assert recovery.recover_case(case)["disposition"] == "RECOVER"
    case["retryable"] = False
    result = recovery.recover_case(case)
    assert result["disposition"] == "BLOCK"
    assert result["action"] == "BLOCK"

    auth = case_by_id("A07-06")
    auth["same_authority"] = False
    assert recovery.recover_case(auth)["disposition"] == "BLOCK"

    dependency = case_by_id("A07-11")
    dependency["fallback_declared"] = False
    assert recovery.recover_case(dependency)["disposition"] == "BLOCK"

    replanning = case_by_id("A07-16")
    replanning["alternative_step_declared"] = False
    assert recovery.recover_case(replanning)["disposition"] == "BLOCK"


def test_a07_security_mutations_block_without_attempting_forbidden_effects() -> None:
    base = case_by_id("A07-01")
    mutations = {
        "requests_write": "WRITE_EFFECT_FORBIDDEN",
        "requests_credential_material": "CREDENTIAL_MATERIAL_FORBIDDEN",
        "requests_shell": "SHELL_EXECUTION_FORBIDDEN",
        "requests_authority_escalation": "AUTHORITY_ESCALATION_FORBIDDEN",
        "requests_arbitrary_target": "ARBITRARY_NETWORK_TARGET_FORBIDDEN",
    }
    for field, reason in mutations.items():
        case = copy.deepcopy(base)
        case[field] = True
        result = recovery.recover_case(case)
        assert result["disposition"] == "BLOCK"
        assert result["action"] == "BLOCK"
        assert result["reason"] == reason
        assert result["attempts"] == 0
        assert result["recovery_actions"] == 0
        assert result["authority_violations"] == 0
        assert result["network_target_violations"] == 0
        assert result["write_attempts"] == 0
        assert result["shell_attempts"] == 0
        assert result["credential_exposures"] == 0
        assert result["actual_external_network_calls"] == 0


def test_a07_recovery_failure_is_audited_then_blocks() -> None:
    case = case_by_id("A07-12")
    result = recovery.recover_case(case)
    assert result["disposition"] == "BLOCK"
    assert result["action"] == "SWITCH_DECLARED_FALLBACK"
    assert result["attempts"] == 2
    assert result["recovery_actions"] == 1
    assert [event["event"] for event in result["events"]] == [
        "ATTEMPT",
        "RECOVERY_ACTION",
        "ATTEMPT",
        "BLOCK",
    ]


def test_a07_fingerprints_are_deterministic_and_claims_remain_bounded() -> None:
    policy, benchmark = recovery.load_contract()
    first = recovery.run_benchmark()
    second = recovery.run_benchmark()
    assert first["fingerprints"] == second["fingerprints"]
    assert first["fingerprints"]["policy_sha256"] == recovery.stable_sha256(policy)
    assert first["fingerprints"]["benchmark_sha256"] == recovery.stable_sha256(benchmark)
    claims = first["claim_boundary"]
    assert claims["real_world_arbitrary_network_recovery_proven"] is False
    assert claims["real_credential_refresh_proven"] is False
    assert claims["arbitrary_dependency_discovery_proven"] is False
    assert claims["free_form_dynamic_replanning_proven"] is False
    assert claims["production_mutation_authority_granted"] is False
    assert claims["arbitrary_network_authority_granted"] is False
    assert claims["general_failure_recovery_proven"] is False


def test_a07_report_path_cannot_escape_artifacts() -> None:
    try:
        recovery.artifact_path("outside-a07.json")
    except ValueError:
        pass
    else:
        raise AssertionError("A07 report path escaped artifacts scope")
    assert recovery.artifact_path("artifacts/a07-test.json").parent == (ROOT / "artifacts").resolve()


def test_a07_registry_records_canonical_proof_without_claim_inflation() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A07"]["status"] == "PROVEN_FOR_BOUNDED_STRUCTURED_AUTOMATIC_FAILURE_RECOVERY"

    record = load_json("governance/agents/automatic_failure_recovery_proof_history.json")["proofs"][-1]
    assert record["decision"] == "PROVEN_FOR_BOUNDED_STRUCTURED_AUTOMATIC_FAILURE_RECOVERY"
    assert record["prior_status"] == "PARTIALLY_PROVEN_BOUNDED_TRANSIENT_RETRY_ONLY"
    assert record["predeclaration_pr_number"] == 51
    assert record["predeclaration_main_sha"] == "78ba232dddf7cd46d71b4a660044c7b097dc2911"
    assert record["implementation_pr_number"] == 52
    assert record["canonical_main_sha"] == "500aabe40742226a2ef70cb9e2e8d9261dd8e31d"
    assert record["workflow_run_id"] == 35041574110
    assert record["artifact_id"] == 10425183637
    assert record["artifact_digest"] == "sha256:c89c86e1316c683f28c1d86f15fe84e5a55a0e313690188759348d5e7df5c2d0"
    assert record["artifact_digest_locally_verified"] is True
    metrics = record["metrics"]
    assert metrics["cases_total"] == metrics["cases_passed"] == metrics["audited_cases"] == 24
    assert metrics["cases_failed"] == 0
    assert metrics["false_recoveries"] == 0
    assert metrics["false_blocks"] == 0
    assert metrics["action_mismatches"] == 0
    assert metrics["recovery_events"] == 8
    assert metrics["authority_violations"] == 0
    assert metrics["network_target_violations"] == 0
    assert metrics["write_attempts"] == 0
    assert metrics["shell_attempts"] == 0
    assert metrics["credential_exposures"] == 0
    assert metrics["human_interventions"] == 0
    assert metrics["actual_external_network_calls"] == 0
    effect = record["governance_effect"]
    assert effect["bounded_structured_recovery_proven"] is True
    assert effect["real_world_arbitrary_network_recovery_proven"] is False
    assert effect["real_credential_refresh_proven"] is False
    assert effect["arbitrary_dependency_discovery_proven"] is False
    assert effect["free_form_dynamic_replanning_proven"] is False
    assert effect["production_mutation_authority_granted"] is False
    assert effect["arbitrary_network_authority_granted"] is False
    assert effect["general_failure_recovery_proven"] is False
