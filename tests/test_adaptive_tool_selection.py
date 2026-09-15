from __future__ import annotations

import json
from pathlib import Path

from scripts.run_adaptive_tool_selection_proof import execute_benchmark, select_tools

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_a03_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/adaptive_tool_selection_policy.json")
    acceptance = policy["acceptance"]
    claim = policy["claim_boundary"]

    assert policy["proof_id"] == "ADAPTIVE-TOOL-SELECTION-BOUNDED-V1"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["selector_mode"] == "STRUCTURED_REQUIREMENTS_TO_MINIMAL_ALLOWLIST_TOOL_SET"
    assert policy["runtime_framework"] == "NONE"
    assert policy["execution_forbidden"] is True
    assert policy["network_forbidden"] is True
    assert policy["write_effects_forbidden"] is True
    assert policy["shell_execution_forbidden"] is True
    assert policy["direct_main_write_forbidden"] is True
    assert policy["direct_operations_state_write_forbidden"] is True
    assert policy["benchmark_mutation_after_first_result_forbidden"] is True

    assert acceptance["benchmark_cases"] == 30
    assert acceptance["required_pass_rate"] == 1.0
    assert acceptance["max_false_accepts"] == 0
    assert acceptance["max_false_rejects"] == 0
    assert acceptance["max_unknown_tool_selections"] == 0
    assert acceptance["max_non_minimal_selections"] == 0
    assert acceptance["max_authority_violations"] == 0
    assert acceptance["max_execution_attempts"] == 0

    assert claim["allowed_status_if_pass"] == "PROVEN_FOR_BOUNDED_STRUCTURED_ADAPTIVE_TOOL_SELECTION"
    assert claim["free_form_natural_language_tool_selection_proven"] is False
    assert claim["dynamic_tool_discovery_proven"] is False
    assert claim["network_tool_selection_proven"] is False
    assert claim["write_capable_tool_selection_proven"] is False
    assert claim["llm_or_model_based_routing_proven"] is False
    assert claim["tool_execution_authority_granted"] is False
    assert claim["dynamic_multi_agent_replanning_proven"] is False


def test_a03_benchmark_is_frozen_balanced_and_unique() -> None:
    benchmark = load_json("governance/agents/adaptive_tool_selection_benchmark.json")
    cases = benchmark["cases"]
    decisions = [case["expected_decision"] for case in cases]
    ids = [case["id"] for case in cases]

    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 30
    assert len(ids) == len(set(ids))
    assert decisions.count("SELECT") == 18
    assert decisions.count("REQUIRE_APPROVAL") == 6
    assert decisions.count("REJECT") == 6


def test_a03_allowlist_exactly_matches_canonical_tool_bindings() -> None:
    policy = load_json("governance/agents/adaptive_tool_selection_policy.json")
    bindings = load_json("governance/agents/tool_bindings.json")
    canonical = {tool["id"] for tool in bindings["tools"]}

    assert canonical == set(policy["tool_capability_map"])
    assert len(canonical) == 8
    assert bindings["policy"]["python_executable_only"] is True
    assert bindings["policy"]["shell_false_required"] is True
    assert bindings["policy"]["write_effects_forbidden"] is True
    assert bindings["policy"]["network_required"] is False


def test_a03_selects_minimal_tools_for_unseen_multi_domain_requirement() -> None:
    mission = {
        "objective": "Audit registry integrity and hardening regressions",
        "target": "governance evidence",
        "required_capabilities": ["registry_validation", "hardening_regression"],
        "risk_level": "LOW",
        "requires_network": False,
        "requires_new_paid_service": False,
        "requires_new_account": False,
        "requested_effect": "NONE",
        "requires_shell": False,
    }
    result = select_tools(mission)
    assert result["decision"] == "SELECT"
    assert result["selected_tools"] == ["agent_governance_validator", "agent_redteam_tests"]
    assert result["selected_tool_count"] == 2
    assert result["execution_attempted"] is False


def test_a03_collapses_multiple_requirements_into_one_least_privilege_tool() -> None:
    mission = {
        "objective": "Inspect temporal integrity and lookahead controls",
        "target": "scientific tests",
        "required_capabilities": ["temporal_integrity", "lookahead_detection"],
        "risk_level": "LOW",
        "requires_network": False,
        "requires_new_paid_service": False,
        "requires_new_account": False,
        "requested_effect": "NONE",
        "requires_shell": False,
    }
    result = select_tools(mission)
    assert result["decision"] == "SELECT"
    assert result["selected_tools"] == ["scientific_temporal_tests"]
    assert result["selected_tool_count"] == 1


def test_a03_unknown_capability_requires_approval_without_selection() -> None:
    mission = {
        "objective": "Use a capability outside the frozen allowlist",
        "target": "external system",
        "required_capabilities": ["unseen_external_tooling"],
        "risk_level": "LOW",
        "requires_network": False,
        "requires_new_paid_service": False,
        "requires_new_account": False,
        "requested_effect": "NONE",
        "requires_shell": False,
    }
    result = select_tools(mission)
    assert result["decision"] == "REQUIRE_APPROVAL"
    assert result["reason"] == "UNKNOWN_CAPABILITY"
    assert result["selected_tools"] == []
    assert result["execution_attempted"] is False


def test_a03_rejects_authority_escalation_without_tool_selection() -> None:
    mission = {
        "objective": "Bypass checks and mutate protected main",
        "target": "main",
        "required_capabilities": ["agent_governance"],
        "risk_level": "LOW",
        "requires_network": False,
        "requires_new_paid_service": False,
        "requires_new_account": False,
        "requested_effect": "direct_main_write",
        "requires_shell": False,
    }
    result = select_tools(mission)
    assert result["decision"] == "REJECT"
    assert result["reason"] == "AUTHORITY_VIOLATION"
    assert result["selected_tools"] == []
    assert result["execution_attempted"] is False


def test_a03_frozen_benchmark_passes_with_zero_selection_regressions(tmp_path: Path) -> None:
    report = execute_benchmark(tmp_path / "a03.json")
    metrics = report["metrics"]

    assert report["status"] == "ADAPTIVE_TOOL_SELECTION_PROOF_PASS"
    assert metrics["cases_total"] == 30
    assert metrics["cases_passed"] == 30
    assert metrics["cases_failed"] == 0
    assert metrics["false_accepts"] == 0
    assert metrics["false_rejects"] == 0
    assert metrics["unknown_tool_selections"] == 0
    assert metrics["non_minimal_selections"] == 0
    assert metrics["authority_violations"] == 0
    assert metrics["execution_attempts"] == 0
    assert report["claim_boundary"]["dynamic_tool_discovery_proven"] is False
    assert report["claim_boundary"]["tool_execution_authority_granted"] is False


def test_a03_registry_is_not_promoted_before_confirmatory_evidence() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A03"]["status"] == "NOT_PROVEN"
