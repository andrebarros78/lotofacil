from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "dynamic_replanning_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "dynamic_replanning_benchmark.json"
AGENTS_PATH = ROOT / "governance" / "agents" / "agents.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _agent_map(agents: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {agent["id"]: agent for agent in agents.get("agents", [])}


def _agent_allows(agent_id: str, action: str, agent_map: dict[str, dict[str, Any]]) -> bool:
    agent = agent_map.get(agent_id)
    return agent is not None and action in agent.get("allowed_actions", [])


def load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy = _load_json(POLICY_PATH)
    benchmark = _load_json(BENCHMARK_PATH)
    agents = _load_json(AGENTS_PATH)

    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A04 schema")
    if policy.get("proof_id") != "DYNAMIC-MULTI-AGENT-REPLANNING-BOUNDED-V1":
        raise ValueError("unexpected A04 proof id")
    if benchmark.get("proof_id") != policy["proof_id"]:
        raise ValueError("benchmark/policy proof id drift")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A04 benchmark is not frozen")
    if policy.get("authority") != "GITHUB_ONLY" or agents.get("authority") != "GITHUB_ONLY":
        raise ValueError("A04 authority drift")
    if policy.get("runtime_framework") != "NONE":
        raise ValueError("external agent runtime framework is not allowed")
    if policy.get("replanner_mode") != "STRUCTURED_STATEFUL_MULTI_AGENT_PLAN_REVISION_SIMULATION":
        raise ValueError("unexpected A04 replanner mode")

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
            raise ValueError(f"A04 safety invariant disabled: {key}")

    acceptance = policy["acceptance"]
    cases = benchmark["cases"]
    if len(cases) != acceptance["benchmark_cases"]:
        raise ValueError("A04 benchmark case count drift")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("duplicate A04 benchmark case id")

    counts = {
        decision: sum(case["expected_decision"] == decision for case in cases)
        for decision in ("REPLAN", "REQUIRE_APPROVAL", "REJECT")
    }
    if counts["REPLAN"] != acceptance["required_replan_cases"]:
        raise ValueError("REPLAN case-count drift")
    if counts["REQUIRE_APPROVAL"] != acceptance["required_approval_cases"]:
        raise ValueError("REQUIRE_APPROVAL case-count drift")
    if counts["REJECT"] != acceptance["required_reject_cases"]:
        raise ValueError("REJECT case-count drift")

    agent_map = _agent_map(agents)
    if not agent_map:
        raise ValueError("canonical agent registry is empty")

    for action, candidates in policy.get("fallback_priority", {}).items():
        if not candidates:
            raise ValueError(f"empty fallback priority for {action}")
        for agent_id in candidates:
            if not _agent_allows(agent_id, action, agent_map):
                raise ValueError(f"invalid fallback assignment: {agent_id}/{action}")

    for event_type, task in policy.get("inserted_review_tasks", {}).items():
        if event_type not in policy.get("allowed_event_types", []):
            raise ValueError(f"review task has unsupported event: {event_type}")
        if not _agent_allows(task["preferred_agent"], task["action"], agent_map):
            raise ValueError(
                f"invalid review assignment: {task['preferred_agent']}/{task['action']}"
            )

    for case in cases:
        for task in case.get("initial_plan", []):
            if not _agent_allows(task["agent_id"], task["action"], agent_map):
                raise ValueError(
                    f"invalid benchmark assignment {case['id']}: "
                    f"{task['agent_id']}/{task['action']}"
                )

    return policy, benchmark, agents


def _find_fallback(
    action: str,
    unavailable: set[str],
    policy: dict[str, Any],
    agent_map: dict[str, dict[str, Any]],
) -> str | None:
    for candidate in policy.get("fallback_priority", {}).get(action, []):
        if candidate in unavailable:
            continue
        if _agent_allows(candidate, action, agent_map):
            return candidate
    return None


def _safe_result(
    *,
    decision: str,
    reason: str,
    completed: bool,
    plan: list[dict[str, Any]],
    transitions: list[dict[str, Any]] | None = None,
    reassignments: int = 0,
    inserted_tasks: int = 0,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "completed": completed,
        "plan": plan,
        "state_transitions": transitions or [],
        "state_transition_count": len(transitions or []),
        "reassignments": reassignments,
        "inserted_tasks": inserted_tasks,
        "authority_violation": False,
        "execution_attempted": False,
        "network_attempted": False,
        "write_attempted": False,
    }


def replan_case(
    case: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    agents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if policy is None:
        policy = _load_json(POLICY_PATH)
    if agents is None:
        agents = _load_json(AGENTS_PATH)

    agent_map = _agent_map(agents)
    plan = copy.deepcopy(case.get("initial_plan", []))
    requested_effect = str(case.get("requested_effect", "NONE"))

    if requested_effect in set(policy.get("rejected_effects", [])):
        return _safe_result(
            decision="REJECT",
            reason="AUTHORITY_VIOLATION",
            completed=False,
            plan=plan,
        )
    if requested_effect != "NONE":
        return _safe_result(
            decision="REJECT",
            reason="WRITE_EFFECT_FORBIDDEN",
            completed=False,
            plan=plan,
        )

    events = list(case.get("events", []))
    approval_types = set(policy.get("approval_event_types", []))
    allowed_types = set(policy.get("allowed_event_types", []))

    for event in events:
        event_type = str(event.get("type", "UNKNOWN_EVENT"))
        if event_type in approval_types:
            return _safe_result(
                decision="REQUIRE_APPROVAL",
                reason=event_type,
                completed=False,
                plan=plan,
            )
        if event_type not in allowed_types:
            return _safe_result(
                decision="REQUIRE_APPROVAL",
                reason="UNKNOWN_EVENT",
                completed=False,
                plan=plan,
            )

    for task in plan:
        if not _agent_allows(task["agent_id"], task["action"], agent_map):
            return _safe_result(
                decision="REQUIRE_APPROVAL",
                reason="INVALID_INITIAL_ASSIGNMENT",
                completed=False,
                plan=plan,
            )

    unavailable: set[str] = set()
    transitions: list[dict[str, Any]] = []
    reassignments = 0
    inserted_tasks = 0

    for event_index, event in enumerate(events, start=1):
        event_type = event["type"]

        if event_type == "AGENT_UNAVAILABLE":
            unavailable_id = str(event.get("agent_id", ""))
            unavailable.add(unavailable_id)
            affected = [task for task in plan if task["agent_id"] == unavailable_id]
            if not affected:
                return _safe_result(
                    decision="REQUIRE_APPROVAL",
                    reason="UNAVAILABLE_AGENT_NOT_IN_PLAN",
                    completed=False,
                    plan=plan,
                    transitions=transitions,
                    reassignments=reassignments,
                    inserted_tasks=inserted_tasks,
                )
            for task in affected:
                replacement = _find_fallback(
                    task["action"], unavailable, policy, agent_map
                )
                if replacement is None:
                    return _safe_result(
                        decision="REQUIRE_APPROVAL",
                        reason="NO_AUTHORIZED_FALLBACK",
                        completed=False,
                        plan=plan,
                        transitions=transitions,
                        reassignments=reassignments,
                        inserted_tasks=inserted_tasks,
                    )
                previous = task["agent_id"]
                task["agent_id"] = replacement
                reassignments += 1
                transitions.append(
                    {
                        "event_index": event_index,
                        "event_type": event_type,
                        "transition": "REASSIGN_TASK",
                        "task_id": task["task_id"],
                        "from_agent": previous,
                        "to_agent": replacement,
                    }
                )
            continue

        review = policy.get("inserted_review_tasks", {}).get(event_type)
        if review is None:
            return _safe_result(
                decision="REQUIRE_APPROVAL",
                reason="NO_PREDECLARED_REPLAN_RULE",
                completed=False,
                plan=plan,
                transitions=transitions,
                reassignments=reassignments,
                inserted_tasks=inserted_tasks,
            )

        action = review["action"]
        preferred = review["preferred_agent"]
        assigned = preferred
        if preferred in unavailable or not _agent_allows(preferred, action, agent_map):
            assigned = _find_fallback(action, unavailable, policy, agent_map)
        if assigned is None or not _agent_allows(assigned, action, agent_map):
            return _safe_result(
                decision="REQUIRE_APPROVAL",
                reason="NO_AUTHORIZED_REVIEW_AGENT",
                completed=False,
                plan=plan,
                transitions=transitions,
                reassignments=reassignments,
                inserted_tasks=inserted_tasks,
            )

        task_id = f"review-{event_index}-{event_type.lower().replace('_', '-')}"
        plan.append({"task_id": task_id, "action": action, "agent_id": assigned})
        inserted_tasks += 1
        transitions.append(
            {
                "event_index": event_index,
                "event_type": event_type,
                "transition": "INSERT_REVIEW_TASK",
                "task_id": task_id,
                "agent_id": assigned,
                "action": action,
            }
        )

    invalid_final = [
        task
        for task in plan
        if task["agent_id"] in unavailable
        or not _agent_allows(task["agent_id"], task["action"], agent_map)
    ]
    if invalid_final:
        return _safe_result(
            decision="REQUIRE_APPROVAL",
            reason="INVALID_FINAL_ASSIGNMENT",
            completed=False,
            plan=plan,
            transitions=transitions,
            reassignments=reassignments,
            inserted_tasks=inserted_tasks,
        )

    return _safe_result(
        decision="REPLAN",
        reason="BOUNDED_PREDECLARED_REPLAN_APPLIED",
        completed=True,
        plan=plan,
        transitions=transitions,
        reassignments=reassignments,
        inserted_tasks=inserted_tasks,
    )


def static_baseline_case(case: dict[str, Any]) -> dict[str, Any]:
    """Frozen comparator: fixed plan, no reassignment and no task insertion."""
    events = list(case.get("events", []))
    if case.get("expected_decision") != "REPLAN":
        return {"completed": False, "reason": "OUTSIDE_REPLAN_COMPARATOR"}
    if events:
        return {"completed": False, "reason": "STATIC_PLAN_CANNOT_ADAPT"}
    return {"completed": True, "reason": "NO_ADAPTATION_REQUIRED"}


def execute_benchmark(output_path: Path | None = None) -> dict[str, Any]:
    policy, benchmark, agents = load_contract()
    agent_map = _agent_map(agents)
    results: list[dict[str, Any]] = []

    authority_violations = 0
    execution_attempts = 0
    network_attempts = 0
    write_attempts = 0
    invalid_agent_assignments = 0
    cases_with_state_transition = 0
    dynamic_replan_completed = 0
    static_replan_completed = 0

    for case in benchmark["cases"]:
        actual = replan_case(case, policy=policy, agents=agents)
        expected_decision = case["expected_decision"]
        expected_reason = case.get("expected_reason")

        decision_match = actual["decision"] == expected_decision
        reason_match = expected_reason is None or actual.get("reason") == expected_reason
        completion_match = actual["completed"] is case.get("expected_completion", False)
        transitions_match = actual["state_transition_count"] >= case.get("min_state_transitions", 0)
        reassignments_match = actual["reassignments"] >= case.get("min_reassignments", 0)
        inserted_match = actual["inserted_tasks"] >= case.get("min_inserted_tasks", 0)

        final_invalid = sum(
            1
            for task in actual.get("plan", [])
            if not _agent_allows(task["agent_id"], task["action"], agent_map)
        )
        invalid_agent_assignments += final_invalid

        if actual.get("authority_violation") is True:
            authority_violations += 1
        if actual.get("execution_attempted") is True:
            execution_attempts += 1
        if actual.get("network_attempted") is True:
            network_attempts += 1
        if actual.get("write_attempted") is True:
            write_attempts += 1
        if actual["state_transition_count"] > 0:
            cases_with_state_transition += 1

        baseline = static_baseline_case(case)
        if expected_decision == "REPLAN":
            if actual["completed"] is True:
                dynamic_replan_completed += 1
            if baseline["completed"] is True:
                static_replan_completed += 1

        passed = (
            decision_match
            and reason_match
            and completion_match
            and transitions_match
            and reassignments_match
            and inserted_match
            and final_invalid == 0
        )
        results.append(
            {
                "id": case["id"],
                "expected_decision": expected_decision,
                "expected_reason": expected_reason,
                "actual": actual,
                "static_baseline": baseline,
                "passed": passed,
            }
        )

    cases_total = len(results)
    cases_passed = sum(item["passed"] for item in results)
    cases_failed = cases_total - cases_passed
    pass_rate = cases_passed / cases_total if cases_total else 0.0
    replan_cases_total = sum(
        case["expected_decision"] == "REPLAN" for case in benchmark["cases"]
    )
    dynamic_rate = dynamic_replan_completed / replan_cases_total if replan_cases_total else 0.0
    static_rate = static_replan_completed / replan_cases_total if replan_cases_total else 0.0
    improvement = dynamic_rate - static_rate

    metrics = {
        "cases_total": cases_total,
        "cases_passed": cases_passed,
        "cases_failed": cases_failed,
        "pass_rate": pass_rate,
        "replan_cases_total": replan_cases_total,
        "dynamic_replan_completed": dynamic_replan_completed,
        "dynamic_replan_completion_rate": dynamic_rate,
        "static_replan_completed": static_replan_completed,
        "static_replan_completion_rate": static_rate,
        "completion_rate_improvement_over_static": improvement,
        "authority_violations": authority_violations,
        "execution_attempts": execution_attempts,
        "network_attempts": network_attempts,
        "write_attempts": write_attempts,
        "invalid_agent_assignments": invalid_agent_assignments,
        "cases_with_state_transition": cases_with_state_transition,
        "human_interventions": 0,
    }

    acceptance = policy["acceptance"]
    accepted = (
        pass_rate >= acceptance["required_dynamic_pass_rate"]
        and improvement >= acceptance["required_min_completion_rate_improvement_over_static"]
        and authority_violations <= acceptance["max_authority_violations"]
        and execution_attempts <= acceptance["max_execution_attempts"]
        and network_attempts <= acceptance["max_network_attempts"]
        and write_attempts <= acceptance["max_write_attempts"]
        and invalid_agent_assignments <= acceptance["max_invalid_agent_assignments"]
        and cases_with_state_transition >= acceptance["min_cases_with_state_transition"]
    )

    report = {
        "schema_version": 1,
        "proof_id": policy["proof_id"],
        "gap_id": policy["gap_id"],
        "status": "DYNAMIC_REPLANNING_PROOF_PASS" if accepted else "DYNAMIC_REPLANNING_PROOF_FAIL",
        "authority": policy["authority"],
        "replanner_mode": policy["replanner_mode"],
        "runtime_framework": policy["runtime_framework"],
        "policy_fingerprint_sha256": _stable_sha256(policy),
        "benchmark_fingerprint_sha256": _stable_sha256(benchmark),
        "agents_fingerprint_sha256": _stable_sha256(agents),
        "metrics": metrics,
        "claim_boundary": policy["claim_boundary"],
        "limitations": [
            "Structured frozen benchmark only",
            "State transitions are simulated, not concurrent real-agent execution",
            "No tool execution, shell, network, write effect, merge, or production mutation occurs",
            "No free-form natural-language or LLM/model-based replanning claim is established",
            "No unbounded agent creation or production replanning authority is granted",
        ],
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
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = execute_benchmark(args.output)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "DYNAMIC_REPLANNING_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
