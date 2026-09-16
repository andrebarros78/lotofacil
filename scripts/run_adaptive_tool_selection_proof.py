from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "adaptive_tool_selection_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "adaptive_tool_selection_benchmark.json"
TOOL_BINDINGS_PATH = ROOT / "governance" / "agents" / "tool_bindings.json"

AUTHORITY_EFFECTS = {
    "direct_main_write",
    "direct_operations_state_write",
    "bypass_ruleset",
    "merge_without_required_checks",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy = _load_json(POLICY_PATH)
    benchmark = _load_json(BENCHMARK_PATH)
    bindings = _load_json(TOOL_BINDINGS_PATH)

    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A03 schema")
    if policy.get("proof_id") != "ADAPTIVE-TOOL-SELECTION-BOUNDED-V1":
        raise ValueError("unexpected A03 proof id")
    if benchmark.get("proof_id") != policy["proof_id"]:
        raise ValueError("benchmark/policy proof id drift")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A03 benchmark is not frozen")
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("A03 authority drift")
    if policy.get("runtime_framework") != "NONE":
        raise ValueError("external runtime framework is not allowed")
    for key in (
        "execution_forbidden",
        "network_forbidden",
        "write_effects_forbidden",
        "shell_execution_forbidden",
        "direct_main_write_forbidden",
        "direct_operations_state_write_forbidden",
        "benchmark_mutation_after_first_result_forbidden",
    ):
        if policy.get(key) is not True:
            raise ValueError(f"A03 safety invariant disabled: {key}")

    binding_policy = bindings.get("policy", {})
    if binding_policy.get("python_executable_only") is not True:
        raise ValueError("tool binding python-only invariant disabled")
    if binding_policy.get("shell_false_required") is not True:
        raise ValueError("tool binding shell invariant disabled")
    if binding_policy.get("write_effects_forbidden") is not True:
        raise ValueError("tool binding write invariant disabled")
    if binding_policy.get("network_required") is not False:
        raise ValueError("tool binding network invariant drift")

    canonical_ids = {tool["id"] for tool in bindings.get("tools", [])}
    policy_ids = set(policy.get("tool_capability_map", {}))
    if canonical_ids != policy_ids:
        raise ValueError("A03 allowlist must exactly match canonical tool bindings")
    if not canonical_ids:
        raise ValueError("canonical tool allowlist must not be empty")

    acceptance = policy["acceptance"]
    cases = benchmark["cases"]
    if len(cases) != acceptance["benchmark_cases"]:
        raise ValueError("benchmark case count drift")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("duplicate A03 benchmark case id")

    counts = {
        decision: sum(case["expected_decision"] == decision for case in cases)
        for decision in ("SELECT", "REQUIRE_APPROVAL", "REJECT")
    }
    if counts["SELECT"] != acceptance["required_select_cases"]:
        raise ValueError("SELECT case-count drift")
    if counts["REQUIRE_APPROVAL"] != acceptance["required_approval_cases"]:
        raise ValueError("REQUIRE_APPROVAL case-count drift")
    if counts["REJECT"] != acceptance["required_reject_cases"]:
        raise ValueError("REJECT case-count drift")

    return policy, benchmark, bindings


def _known_capabilities(policy: dict[str, Any]) -> set[str]:
    return {
        capability
        for capabilities in policy["tool_capability_map"].values()
        for capability in capabilities
    }


def _minimal_cover(
    required_capabilities: list[str],
    tool_capability_map: dict[str, list[str]],
) -> list[str]:
    required = set(required_capabilities)
    tool_ids = sorted(tool_capability_map)
    for count in range(1, len(tool_ids) + 1):
        for combo in itertools.combinations(tool_ids, count):
            covered: set[str] = set()
            for tool_id in combo:
                covered.update(tool_capability_map[tool_id])
            if required <= covered:
                return list(combo)
    raise ValueError("known capability set has no allowlisted cover")


def select_tools(
    mission: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if policy is None:
        policy = _load_json(POLICY_PATH)

    required = list(mission.get("required_capabilities", []))
    effect = str(mission.get("requested_effect", "NONE"))
    risk = str(mission.get("risk_level", "LOW"))

    if effect in AUTHORITY_EFFECTS:
        return {
            "decision": "REJECT",
            "reason": "AUTHORITY_VIOLATION",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if mission.get("requires_shell") is True:
        return {
            "decision": "REJECT",
            "reason": "SHELL_EXECUTION_FORBIDDEN",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if effect != "NONE":
        return {
            "decision": "REJECT",
            "reason": "WRITE_EFFECT_FORBIDDEN",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if not required:
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "MISSING_REQUIRED_CAPABILITIES",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if risk == "HIGH":
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "HIGH_RISK",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if mission.get("requires_network") is True:
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "NETWORK_REQUIRED",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if mission.get("requires_new_paid_service") is True:
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "NEW_PAID_SERVICE_REQUIRED",
            "selected_tools": [],
            "execution_attempted": False,
        }
    if mission.get("requires_new_account") is True:
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "NEW_ACCOUNT_REQUIRED",
            "selected_tools": [],
            "execution_attempted": False,
        }

    known = _known_capabilities(policy)
    unknown = sorted(set(required) - known)
    if unknown:
        return {
            "decision": "REQUIRE_APPROVAL",
            "reason": "UNKNOWN_CAPABILITY",
            "unknown_capabilities": unknown,
            "selected_tools": [],
            "execution_attempted": False,
        }

    selected = _minimal_cover(required, policy["tool_capability_map"])
    return {
        "decision": "SELECT",
        "reason": "MINIMAL_ALLOWLIST_COVER",
        "selected_tools": selected,
        "selected_tool_count": len(selected),
        "execution_attempted": False,
    }


def _authority_condition_present(mission: dict[str, Any]) -> bool:
    return (
        mission.get("requested_effect", "NONE") != "NONE"
        or mission.get("requires_shell") is True
        or mission.get("requires_network") is True
        or mission.get("requires_new_paid_service") is True
        or mission.get("requires_new_account") is True
        or mission.get("risk_level") == "HIGH"
    )


def execute_benchmark(output_path: Path | None = None) -> dict[str, Any]:
    policy, benchmark, bindings = load_contract()
    allowlist = set(policy["tool_capability_map"])
    results: list[dict[str, Any]] = []

    false_accepts = 0
    false_rejects = 0
    unknown_tool_selections = 0
    non_minimal_selections = 0
    authority_violations = 0
    execution_attempts = 0

    for case in benchmark["cases"]:
        mission = case["mission"]
        expected_decision = case["expected_decision"]
        expected_tools = sorted(case.get("expected_tools", []))
        actual = select_tools(mission, policy=policy)
        actual_tools = sorted(actual.get("selected_tools", []))

        decision_match = actual["decision"] == expected_decision
        reason_match = (
            True
            if "expected_reason" not in case
            else actual.get("reason") == case["expected_reason"]
        )
        tools_match = actual_tools == expected_tools
        passed = decision_match and reason_match and tools_match

        if expected_decision != "SELECT" and actual["decision"] == "SELECT":
            false_accepts += 1
        if expected_decision == "SELECT" and actual["decision"] != "SELECT":
            false_rejects += 1

        unknown_selected = [tool_id for tool_id in actual_tools if tool_id not in allowlist]
        unknown_tool_selections += len(unknown_selected)

        if actual["decision"] == "SELECT":
            minimal = _minimal_cover(
                mission["required_capabilities"],
                policy["tool_capability_map"],
            )
            if len(actual_tools) != len(minimal):
                non_minimal_selections += 1
            if _authority_condition_present(mission):
                authority_violations += 1

        if actual.get("execution_attempted") is True:
            execution_attempts += 1

        results.append(
            {
                "id": case["id"],
                "expected_decision": expected_decision,
                "expected_reason": case.get("expected_reason"),
                "expected_tools": expected_tools,
                "actual": actual,
                "passed": passed,
            }
        )

    cases_total = len(results)
    cases_passed = sum(item["passed"] for item in results)
    cases_failed = cases_total - cases_passed
    pass_rate = cases_passed / cases_total if cases_total else 0.0

    metrics = {
        "cases_total": cases_total,
        "cases_passed": cases_passed,
        "cases_failed": cases_failed,
        "pass_rate": pass_rate,
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "unknown_tool_selections": unknown_tool_selections,
        "non_minimal_selections": non_minimal_selections,
        "authority_violations": authority_violations,
        "execution_attempts": execution_attempts,
        "human_interventions": 0,
        "canonical_tool_count": len(allowlist),
    }

    acceptance = policy["acceptance"]
    passed = (
        pass_rate >= acceptance["required_pass_rate"]
        and false_accepts <= acceptance["max_false_accepts"]
        and false_rejects <= acceptance["max_false_rejects"]
        and unknown_tool_selections <= acceptance["max_unknown_tool_selections"]
        and non_minimal_selections <= acceptance["max_non_minimal_selections"]
        and authority_violations <= acceptance["max_authority_violations"]
        and execution_attempts <= acceptance["max_execution_attempts"]
    )

    report = {
        "schema_version": 1,
        "proof_id": policy["proof_id"],
        "gap_id": policy["gap_id"],
        "status": "ADAPTIVE_TOOL_SELECTION_PROOF_PASS"
        if passed
        else "ADAPTIVE_TOOL_SELECTION_PROOF_FAIL",
        "authority": policy["authority"],
        "selector_mode": policy["selector_mode"],
        "policy_fingerprint_sha256": _stable_sha256(policy),
        "benchmark_fingerprint_sha256": _stable_sha256(benchmark),
        "tool_bindings_fingerprint_sha256": _stable_sha256(bindings),
        "metrics": metrics,
        "claim_boundary": policy["claim_boundary"],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "results": results,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = execute_benchmark(args.output)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ADAPTIVE_TOOL_SELECTION_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
