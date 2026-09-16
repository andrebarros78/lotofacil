from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "automatic_failure_recovery_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "automatic_failure_recovery_benchmark.json"
PROOF_ID = "AUTOMATIC-FAILURE-RECOVERY-BOUNDED-V1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = load_json(POLICY_PATH)
    benchmark = load_json(BENCHMARK_PATH)

    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A07 schema")
    if policy.get("proof_id") != PROOF_ID or benchmark.get("proof_id") != PROOF_ID:
        raise ValueError("A07 proof id drift")
    if policy.get("gap_id") != "GAP-A07" or benchmark.get("gap_id") != "GAP-A07":
        raise ValueError("A07 gap id drift")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A07 benchmark is not frozen")
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("A07 authority drift")
    if policy.get("runtime_framework") != "NONE":
        raise ValueError("A07 external runtime framework is forbidden")
    if policy.get("execution_scope") != "CONTROLLED_STRUCTURED_SIMULATION_ONLY":
        raise ValueError("A07 execution scope drift")

    guard = policy.get("policy", {})
    for key in (
        "automatic_recovery_required",
        "human_intervention_forbidden",
        "hidden_failure_forbidden",
        "failed_attempt_must_be_recorded",
        "authority_escalation_forbidden",
        "arbitrary_network_target_forbidden",
        "provider_write_requests_forbidden",
        "shell_execution_forbidden",
        "credential_material_forbidden",
        "benchmark_mutation_after_first_result_forbidden",
    ):
        if guard.get(key) is not True:
            raise ValueError(f"A07 safety invariant disabled: {key}")

    cases = benchmark.get("cases", [])
    acceptance = policy.get("acceptance", {})
    if len(cases) != acceptance.get("benchmark_cases"):
        raise ValueError("A07 benchmark case-count drift")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("duplicate A07 benchmark case id")
    if guard.get("max_recovery_actions_per_case") != 1:
        raise ValueError("unexpected A07 recovery action bound")
    if guard.get("max_total_attempts_per_case") != 2:
        raise ValueError("unexpected A07 attempt bound")

    declared_classes = set(policy.get("failure_classes", {}))
    for case in cases:
        if case.get("failure_class") not in declared_classes:
            raise ValueError(f"unknown A07 failure class: {case.get('failure_class')}")
        outcomes = case.get("outcomes")
        if not isinstance(outcomes, list) or not outcomes or len(outcomes) > 2:
            raise ValueError(f"invalid A07 outcome sequence: {case.get('id')}")
        if any(outcome not in {"PASS", "FAIL"} for outcome in outcomes):
            raise ValueError(f"invalid A07 outcome token: {case.get('id')}")
        if case.get("expected") not in {"PASS", "RECOVER", "BLOCK"}:
            raise ValueError(f"invalid A07 expected disposition: {case.get('id')}")

    return policy, benchmark


def _security_block_reason(case: dict[str, Any]) -> str | None:
    checks = (
        ("requests_write", "WRITE_EFFECT_FORBIDDEN"),
        ("requests_credential_material", "CREDENTIAL_MATERIAL_FORBIDDEN"),
        ("requests_shell", "SHELL_EXECUTION_FORBIDDEN"),
        ("requests_authority_escalation", "AUTHORITY_ESCALATION_FORBIDDEN"),
        ("requests_arbitrary_target", "ARBITRARY_NETWORK_TARGET_FORBIDDEN"),
    )
    for key, reason in checks:
        if case.get(key) is True:
            return reason
    return None


def _select_recovery_action(case: dict[str, Any]) -> tuple[str, str]:
    failure_class = str(case.get("failure_class", "UNKNOWN_FAILURE"))

    if failure_class == "NETWORK_TRANSIENT":
        if case.get("retryable") is True and case.get("same_target") is True:
            return "RETRY_SAME_OPERATION", "BOUNDED_TRANSIENT_RETRY"
        return "BLOCK", "NETWORK_RETRY_NOT_AUTHORIZED"

    if failure_class == "NETWORK_PERSISTENT":
        return "BLOCK", "PERSISTENT_NETWORK_FAILURE"

    if failure_class == "AUTHORIZATION_EXPIRED_REFRESHABLE":
        if (
            case.get("refresh_capability_declared") is True
            and case.get("same_authority") is True
        ):
            return "REFRESH_DECLARED_AUTH_CONTEXT", "DECLARED_AUTH_REFRESH"
        return "BLOCK", "AUTH_REFRESH_NOT_AUTHORIZED"

    if failure_class == "AUTHORIZATION_FORBIDDEN":
        return "BLOCK", "AUTHORIZATION_FORBIDDEN"

    if failure_class == "DEPENDENCY_UNAVAILABLE_WITH_FALLBACK":
        if case.get("fallback_declared") is True and case.get("fallback_same_authority") is True:
            return "SWITCH_DECLARED_FALLBACK", "DECLARED_DEPENDENCY_FALLBACK"
        return "BLOCK", "DEPENDENCY_FALLBACK_NOT_AUTHORIZED"

    if failure_class == "DEPENDENCY_UNAVAILABLE_NO_FALLBACK":
        return "BLOCK", "NO_DECLARED_DEPENDENCY_FALLBACK"

    if failure_class == "REPLANNABLE_STEP_FAILURE":
        if (
            case.get("alternative_step_declared") is True
            and case.get("alternative_same_authority") is True
        ):
            return "REPLAN_TO_DECLARED_ALTERNATIVE", "DECLARED_BOUNDED_REPLAN"
        return "BLOCK", "REPLAN_NOT_AUTHORIZED"

    if failure_class == "NON_REPLANNABLE_STEP_FAILURE":
        return "BLOCK", "NON_REPLANNABLE_FAILURE"

    return "BLOCK", "UNKNOWN_FAILURE_CLASS"


def recover_case(case: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    outcomes = list(case.get("outcomes", []))
    safety_reason = _security_block_reason(case)

    base = {
        "case_id": case.get("id"),
        "failure_class": case.get("failure_class"),
        "recovery_actions": 0,
        "attempts": 0,
        "authority_violations": 0,
        "network_target_violations": 0,
        "write_attempts": 0,
        "shell_attempts": 0,
        "credential_exposures": 0,
        "human_interventions": 0,
        "actual_external_network_calls": 0,
        "events": events,
    }

    if safety_reason is not None:
        events.append({"event": "SAFETY_BLOCK", "reason": safety_reason})
        return {
            **base,
            "disposition": "BLOCK",
            "action": "BLOCK",
            "reason": safety_reason,
        }

    if not outcomes:
        events.append({"event": "SAFETY_BLOCK", "reason": "MISSING_OUTCOME_SEQUENCE"})
        return {**base, "disposition": "BLOCK", "action": "BLOCK", "reason": "MISSING_OUTCOME_SEQUENCE"}

    first = outcomes[0]
    base["attempts"] = 1
    events.append({"event": "ATTEMPT", "attempt": 1, "outcome": first})

    if first == "PASS":
        return {**base, "disposition": "PASS", "action": "NONE", "reason": "INITIAL_ATTEMPT_PASS"}

    action, reason = _select_recovery_action(case)
    if action == "BLOCK":
        events.append({"event": "BLOCK", "reason": reason})
        return {**base, "disposition": "BLOCK", "action": "BLOCK", "reason": reason}

    base["recovery_actions"] = 1
    events.append({"event": "RECOVERY_ACTION", "action": action, "reason": reason})

    if len(outcomes) < 2:
        events.append({"event": "BLOCK", "reason": "NO_POST_RECOVERY_OUTCOME"})
        return {
            **base,
            "disposition": "BLOCK",
            "action": action,
            "reason": "NO_POST_RECOVERY_OUTCOME",
        }

    second = outcomes[1]
    base["attempts"] = 2
    events.append({"event": "ATTEMPT", "attempt": 2, "outcome": second})
    if second == "PASS":
        events.append({"event": "RECOVERY_COMPLETE", "action": action})
        return {**base, "disposition": "RECOVER", "action": action, "reason": reason}

    events.append({"event": "BLOCK", "reason": "RECOVERY_ACTION_EXHAUSTED"})
    return {
        **base,
        "disposition": "BLOCK",
        "action": action,
        "reason": "RECOVERY_ACTION_EXHAUSTED",
    }


def evaluate_case(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected = str(case["expected"])
    expected_action = str(case["expected_action"])
    disposition_match = actual["disposition"] == expected
    action_match = actual["action"] == expected_action
    safety_ok = all(
        actual[key] == 0
        for key in (
            "authority_violations",
            "network_target_violations",
            "write_attempts",
            "shell_attempts",
            "credential_exposures",
            "human_interventions",
            "actual_external_network_calls",
        )
    )
    bounds_ok = actual["recovery_actions"] <= 1 and actual["attempts"] <= 2
    audit_ok = bool(actual["events"])
    return {
        "case_id": case["id"],
        "expected": expected,
        "actual": actual["disposition"],
        "expected_action": expected_action,
        "actual_action": actual["action"],
        "disposition_match": disposition_match,
        "action_match": action_match,
        "safety_ok": safety_ok,
        "bounds_ok": bounds_ok,
        "audit_ok": audit_ok,
        "pass": disposition_match and action_match and safety_ok and bounds_ok and audit_ok,
    }


def run_benchmark() -> dict[str, Any]:
    policy, benchmark = load_contract()
    case_results: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []

    for case in benchmark["cases"]:
        actual = recover_case(case)
        evaluation = evaluate_case(case, actual)
        case_results.append(actual)
        evaluations.append(evaluation)

    total = len(evaluations)
    passed = sum(item["pass"] for item in evaluations)
    failed = total - passed
    false_recoveries = sum(
        result["disposition"] == "RECOVER" and case["expected"] != "RECOVER"
        for case, result in zip(benchmark["cases"], case_results, strict=True)
    )
    false_blocks = sum(
        result["disposition"] == "BLOCK" and case["expected"] != "BLOCK"
        for case, result in zip(benchmark["cases"], case_results, strict=True)
    )
    action_mismatches = sum(not item["action_match"] for item in evaluations)
    authority_violations = sum(item["authority_violations"] for item in case_results)
    network_target_violations = sum(item["network_target_violations"] for item in case_results)
    write_attempts = sum(item["write_attempts"] for item in case_results)
    shell_attempts = sum(item["shell_attempts"] for item in case_results)
    credential_exposures = sum(item["credential_exposures"] for item in case_results)
    human_interventions = sum(item["human_interventions"] for item in case_results)
    external_network_calls = sum(item["actual_external_network_calls"] for item in case_results)
    recovery_events = sum(item["recovery_actions"] for item in case_results)
    audited_events = sum(bool(item["events"]) for item in case_results)

    acceptance = policy["acceptance"]
    success = (
        total == acceptance["benchmark_cases"]
        and passed == total
        and false_recoveries <= acceptance["max_false_recoveries"]
        and false_blocks <= acceptance["max_false_blocks"]
        and action_mismatches == 0
        and authority_violations <= acceptance["max_authority_violations"]
        and network_target_violations <= acceptance["max_network_target_violations"]
        and write_attempts <= acceptance["max_write_attempts"]
        and shell_attempts <= acceptance["max_shell_attempts"]
        and credential_exposures <= acceptance["max_credential_exposures"]
        and human_interventions <= acceptance["max_human_interventions"]
        and audited_events == total
    )

    return {
        "schema_version": 1,
        "proof_id": PROOF_ID,
        "gap_id": "GAP-A07",
        "status": "AUTOMATIC_FAILURE_RECOVERY_PROOF_PASS" if success else "AUTOMATIC_FAILURE_RECOVERY_PROOF_FAIL",
        "authority": policy["authority"],
        "runtime_framework": policy["runtime_framework"],
        "execution_scope": policy["execution_scope"],
        "environment": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "fingerprints": {
            "policy_sha256": stable_sha256(policy),
            "benchmark_sha256": stable_sha256(benchmark),
        },
        "metrics": {
            "cases_total": total,
            "cases_passed": passed,
            "cases_failed": failed,
            "pass_rate": passed / total if total else 0.0,
            "false_recoveries": false_recoveries,
            "false_blocks": false_blocks,
            "action_mismatches": action_mismatches,
            "recovery_events": recovery_events,
            "authority_violations": authority_violations,
            "network_target_violations": network_target_violations,
            "write_attempts": write_attempts,
            "shell_attempts": shell_attempts,
            "credential_exposures": credential_exposures,
            "human_interventions": human_interventions,
            "actual_external_network_calls": external_network_calls,
            "audited_cases": audited_events,
        },
        "evaluations": evaluations,
        "case_results": case_results,
        "claim_boundary": policy["claim_boundary"],
        "limitations": [
            "Recovery behavior is proven only for the frozen structured simulation benchmark.",
            "No arbitrary live-network recovery is executed or proven by this benchmark.",
            "Authorization refresh is simulated from declared state and does not refresh a real credential.",
            "Dependency fallback is selected only from predeclared structured state; arbitrary discovery is not proven.",
            "Replanning is limited to a predeclared same-authority alternative and is not free-form dynamic replanning.",
            "No production mutation, shell execution, arbitrary network authority or credential material is permitted.",
        ],
    }


def artifact_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    artifacts = (ROOT / "artifacts").resolve()
    if path != artifacts and artifacts not in path.parents:
        raise ValueError("A07 proof output must remain under artifacts/")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded GAP-A07 automatic failure recovery proof.")
    parser.add_argument("--report", default="artifacts/automatic_failure_recovery_proof.json")
    args = parser.parse_args()

    report = run_benchmark()
    report_path = artifact_path(args.report)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, sort_keys=True))
    return 0 if report["status"] == "AUTOMATIC_FAILURE_RECOVERY_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
