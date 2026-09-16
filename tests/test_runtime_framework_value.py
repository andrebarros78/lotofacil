from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_runtime_framework_value_experiment as a10  # noqa: E402


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_a10_policy_is_bounded_noncanonical_and_predeclared() -> None:
    policy = load_json("governance/agents/runtime_framework_value_policy.json")
    assert policy["proof_id"] == "AGENT-RUNTIME-FRAMEWORK-VALUE-BOUNDED-V1"
    assert policy["gap_id"] == "GAP-A10"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["experiment_mode"] == "NON_CANONICAL_PINNED_FRAMEWORK_COMPARISON"
    assert policy["canonical_runtime_framework"] == "NONE"
    assert policy["candidate"]["id"] == "langgraph"
    assert policy["candidate"]["version"] == "1.2.11"
    assert policy["candidate"]["checkpoint_version"] == "3.1.1"
    assert policy["candidate"]["known_upstream_risk"]["issue"] == "langchain-ai/langgraph#8834"
    assert policy["candidate"]["known_upstream_risk"]["must_remain_in_benchmark"] is True
    assert policy["decision_rule"]["automatic_production_adoption"] is False
    assert policy["claim_boundary"]["canonical_framework_adoption_authorized"] is False
    assert policy["claim_boundary"]["production_runtime_value_proven"] is False
    assert policy["claim_boundary"]["general_agent_framework_superiority_proven"] is False


def test_a10_benchmark_is_frozen_unique_and_contains_upstream_risk() -> None:
    policy, benchmark = a10.load_contract()
    cases = benchmark["cases"]
    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24
    assert sum(case["fault"]["kind"] != "NONE" for case in cases) == 16
    assert sum(case["class"] == "CONDITIONAL_ROUTER_FAILURE_RESUME" for case in cases) == 4
    assert benchmark["classes"]["CONDITIONAL_ROUTER_FAILURE_RESUME"]["known_upstream_risk"] == "langchain-ai/langgraph#8834"
    assert policy["acceptance"]["benchmark_cases"] == 24
    assert policy["acceptance"]["candidate_hidden_failure_successes_max"] == 0


def test_a10_acquisition_remains_noncanonical_reference_target() -> None:
    doc = load_json("governance/agents/acquisitions.json")
    item = next(item for item in doc["acquisitions"] if item["id"] == "langgraph")
    assert item["decision"] == "ACQUIRED_AS_REFERENCE_AND_ADAPTER_TARGET"
    assert item["runtime_dependency"] is False
    assert item["experiment"]["authorization"] == "PINNED_NON_CANONICAL_ONLY"
    assert item["experiment"]["canonical_dependency"] is False


def test_a10_canonical_pyproject_has_no_langgraph_runtime_dependency() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "langgraph" not in text


def test_a10_baseline_reports_unsupported_classes_instead_of_faking_support(tmp_path: Path) -> None:
    _, benchmark = a10.load_contract()
    results = [a10.run_baseline_case(case, tmp_path) for case in benchmark["cases"]]
    unsupported = [result for result in results if not result["supported"]]
    assert len(unsupported) == 12
    assert all(result["error"] == "UNSUPPORTED_BY_FROZEN_BASELINE" for result in unsupported)
    supported = [result for result in results if result["supported"]]
    assert len(supported) == 12
    assert all(result["correct_final_state"] for result in supported)


def test_a10_decision_requires_correct_state_and_no_hidden_success() -> None:
    policy, _ = a10.load_contract()
    baseline = {
        "completion_rate": 0.5,
        "recoverable_fault_recovery_rate": 0.5,
        "human_interventions": 0,
    }
    candidate = {
        "completion_rate": 0.9,
        "recoverable_fault_recovery_rate": 0.75,
        "human_interventions": 0,
        "correct_final_state_rate": 0.9,
        "hidden_failure_successes": 1,
    }
    decision, gates = a10.decide(policy, baseline, candidate, dependency_delta=10)
    assert decision == "NOT_JUSTIFIED_FOR_CURRENT_BOUNDED_BASELINE"
    assert gates["meaningful_primary_improvement"] is True
    assert gates["candidate_correctness_gate"] is False
    assert gates["candidate_hidden_failure_gate"] is False
    assert gates["value_established"] is False


def test_a10_full_candidate_experiment_when_pinned_runtime_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langgraph")
    if not a10.candidate_runtime_available():
        pytest.skip("exact pinned A10 candidate runtime not installed")
    baseline_count = len(list(a10.importlib.metadata.distributions())) - 1
    monkeypatch.setenv("A10_BASELINE_DISTRIBUTIONS_COUNT", str(max(0, baseline_count)))
    report = a10.run_experiment()
    assert report["status"] == "RUNTIME_FRAMEWORK_VALUE_EXPERIMENT_COMPLETE"
    assert report["decision"] in {
        "PROVEN_FOR_BOUNDED_LANGGRAPH_RUNTIME_VALUE_EXPERIMENT",
        "NOT_JUSTIFIED_FOR_CURRENT_BOUNDED_BASELINE",
    }
    assert report["baseline_metrics"]["cases_total"] == 24
    assert report["candidate_metrics"]["cases_total"] == 24
    assert report["baseline_metrics"]["unsupported_cases"] == 12
    assert report["safety"]["authority_violations"] == 0
    assert report["safety"]["runtime_external_network_calls"] == 0
    assert report["safety"]["external_model_calls"] == 0
    assert report["safety"]["paid_calls"] == 0
    assert report["claim_boundary"]["canonical_framework_adoption_authorized"] is False


def test_a10_report_path_cannot_escape_artifacts() -> None:
    with pytest.raises(ValueError):
        a10.artifact_path("outside-a10.json")
    assert a10.artifact_path("artifacts/a10-runtime-value-test.json").parent == (ROOT / "artifacts").resolve()


def test_a10_registry_and_history_record_conclusive_negative_decision() -> None:
    gaps = {gap["id"]: gap for gap in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A10"]["status"] == "NOT_JUSTIFIED_FOR_CURRENT_BOUNDED_BASELINE"

    proof = load_json("governance/agents/runtime_framework_value_proof_history.json")["proofs"][-1]
    assert proof["decision"] == "NOT_JUSTIFIED_FOR_CURRENT_BOUNDED_BASELINE"
    assert proof["confirmatory_evidence"]["workflow_run_id"] == 35098538835
    assert proof["confirmatory_evidence"]["artifact_id"] == 10447710205
    assert proof["confirmatory_evidence"]["github_sha"] == "2b9a24ff6b83ef54a9f6b34be3f45b6196f3ef63"
    assert proof["metrics"]["candidate"]["correct_final_states"] == 20
    assert proof["metrics"]["candidate"]["hidden_failure_successes"] == 4
    assert proof["metrics"]["dependency_cost"]["runtime_dependency_distributions_delta"] == 29
    assert proof["metrics"]["comparison"]["value_established"] is False
    assert proof["safety"]["authority_violations"] == 0
    assert proof["governance_effect"]["canonical_runtime_framework"] == "NONE"
    assert proof["governance_effect"]["canonical_framework_adoption_authorized"] is False
    assert proof["governance_effect"]["general_agent_framework_inferiority_proven"] is False
