from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "open_ended_planning_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "open_ended_planning_benchmark.json"
AGENTS_PATH = ROOT / "governance" / "agents" / "agents.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy = _load_json(POLICY_PATH)
    benchmark = _load_json(BENCHMARK_PATH)
    agents = _load_json(AGENTS_PATH)

    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A02 schema")
    if policy.get("proof_id") != "OPEN-ENDED-PLANNING-BOUNDED-V1":
        raise ValueError("unexpected A02 proof id")
    if benchmark.get("proof_id") != policy["proof_id"]:
        raise ValueError("benchmark/policy proof id drift")
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("A02 authority drift")
    if policy.get("runtime_framework") != "NONE":
        raise ValueError("A02 baseline must remain framework-independent")
    if policy.get("execution_forbidden") is not True:
        raise ValueError("A02 execution prohibition disabled")
    if policy.get("network_forbidden") is not True:
        raise ValueError("A02 network prohibition disabled")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A02 benchmark is not frozen")

    cases = benchmark.get("cases", [])
    acceptance = policy.get("acceptance", {})
    if len(cases) != acceptance.get("benchmark_cases"):
        raise ValueError("A02 benchmark case count drift")
    ids = [case.get("id") for case in cases]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("A02 benchmark ids invalid")
    decisions = [case.get("expected_decision") for case in cases]
    if decisions.count("PLAN") != acceptance.get("required_plan_cases"):
        raise ValueError("A02 PLAN case count drift")
    if decisions.count("REQUIRE_APPROVAL") != acceptance.get("required_approval_cases"):
        raise ValueError("A02 approval case count drift")
    if decisions.count("REJECT") != acceptance.get("required_reject_cases"):
        raise ValueError("A02 reject case count drift")

    agent_ids = [agent.get("id") for agent in agents.get("agents", [])]
    if None in agent_ids or len(agent_ids) != len(set(agent_ids)):
        raise ValueError("agent registry invalid")
    return policy, benchmark, agents


def _owner_for_action(action: str, agents_doc: dict[str, Any], priority: list[str]) -> str | None:
    owners = {
        agent["id"]
        for agent in agents_doc.get("agents", [])
        if action in agent.get("allowed_actions", [])
    }
    for agent_id in priority:
        if agent_id in owners:
            return agent_id
    return sorted(owners)[0] if owners else None


def _decision(decision: str, reason: str, *, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "steps": steps or [],
        "execution_attempted": False,
        "write_attempted": False,
        "network_attempted": False,
    }


def plan_mission(mission: dict[str, Any]) -> dict[str, Any]:
    policy, _, agents_doc = load_contract()
    requested_actions = mission.get("requested_actions")
    if not isinstance(requested_actions, list) or not requested_actions:
        return _decision("REQUIRE_APPROVAL", "UNKNOWN_ACTION")

    prohibited = set(policy.get("prohibited_actions", []))
    requested_set = set(requested_actions)
    if "scientific_promotion_without_evidence" in requested_set:
        return _decision("REJECT", "SCIENTIFIC_CLAIM_ESCALATION")
    if requested_set & prohibited:
        return _decision("REJECT", "AUTHORITY_VIOLATION")

    if not str(mission.get("target", "")).strip():
        return _decision("REQUIRE_APPROVAL", "MISSING_TARGET")
    criteria = mission.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        return _decision("REQUIRE_APPROVAL", "MISSING_ACCEPTANCE_CRITERIA")
    if mission.get("risk_level") == "HIGH":
        return _decision("REQUIRE_APPROVAL", "HIGH_RISK")
    if mission.get("requires_network") is True:
        return _decision("REQUIRE_APPROVAL", "NETWORK_REQUIRED")
    if mission.get("requires_new_paid_service") is True:
        return _decision("REQUIRE_APPROVAL", "NEW_PAID_SERVICE_REQUIRED")

    priority = list(policy.get("agent_priority", []))
    steps: list[dict[str, Any]] = []
    for ordinal, action in enumerate(requested_actions, start=1):
        owner = _owner_for_action(action, agents_doc, priority)
        if owner is None:
            return _decision("REQUIRE_APPROVAL", "UNKNOWN_ACTION")
        steps.append(
            {
                "ordinal": ordinal,
                "action": action,
                "agent_id": owner,
                "target": mission["target"],
                "execution": "FORBIDDEN_PLAN_ONLY",
            }
        )

    return _decision("PLAN", "BOUNDED_PLAN_READY", steps=steps)


def execute_benchmark(output_path: Path) -> dict[str, Any]:
    policy, benchmark, agents_doc = load_contract()
    prohibited = set(policy["prohibited_actions"])
    results: list[dict[str, Any]] = []
    false_accepts = 0
    false_rejects = 0
    authority_violations = 0
    execution_attempts = 0

    for case in benchmark["cases"]:
        mission = case["mission"]
        actual = plan_mission(mission)
        expected_decision = case["expected_decision"]
        expected_reason = case.get("expected_reason")
        decision_match = actual["decision"] == expected_decision
        reason_match = expected_reason is None or actual["reason"] == expected_reason
        plan_shape_match = True
        if expected_decision == "PLAN":
            plan_shape_match = [step["action"] for step in actual["steps"]] == mission["requested_actions"]
            for step in actual["steps"]:
                owner = _owner_for_action(step["action"], agents_doc, policy["agent_priority"])
                if owner != step["agent_id"]:
                    plan_shape_match = False

        passed = decision_match and reason_match and plan_shape_match
        if expected_decision != "PLAN" and actual["decision"] == "PLAN":
            false_accepts += 1
        if expected_decision == "PLAN" and actual["decision"] != "PLAN":
            false_rejects += 1
        if actual["decision"] == "PLAN" and set(mission["requested_actions"]) & prohibited:
            authority_violations += 1
        execution_attempts += int(bool(actual["execution_attempted"]))

        results.append(
            {
                "case_id": case["id"],
                "expected_decision": expected_decision,
                "expected_reason": expected_reason,
                "actual_decision": actual["decision"],
                "actual_reason": actual["reason"],
                "status": "PASS" if passed else "FAIL",
                "plan_steps": actual["steps"],
                "execution_attempted": actual["execution_attempted"],
            }
        )

    passed_count = sum(item["status"] == "PASS" for item in results)
    failed_count = len(results) - passed_count
    acceptance = policy["acceptance"]
    pass_rate = passed_count / len(results) if results else 0.0
    proof_passed = (
        pass_rate >= acceptance["required_pass_rate"]
        and false_accepts <= acceptance["max_false_accepts"]
        and false_rejects <= acceptance["max_false_rejects"]
        and authority_violations <= acceptance["max_authority_violations"]
        and execution_attempts <= acceptance["max_execution_attempts"]
    )

    report = {
        "schema_version": 1,
        "proof_id": policy["proof_id"],
        "gap_id": policy["gap_id"],
        "status": "OPEN_ENDED_PLANNING_PROOF_PASS" if proof_passed else "OPEN_ENDED_PLANNING_PROOF_FAIL",
        "authority": policy["authority"],
        "planner_mode": policy["planner_mode"],
        "runtime_framework": policy["runtime_framework"],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "metrics": {
            "cases_total": len(results),
            "cases_passed": passed_count,
            "cases_failed": failed_count,
            "pass_rate": pass_rate,
            "false_accepts": false_accepts,
            "false_rejects": false_rejects,
            "authority_violations": authority_violations,
            "execution_attempts": execution_attempts,
            "human_interventions": 0,
        },
        "policy_fingerprint_sha256": _stable_sha256(policy),
        "benchmark_fingerprint_sha256": _stable_sha256(benchmark),
        "results": results,
        "claim_boundary": policy["claim_boundary"],
        "limitations": [
            "This proof covers structured unseen mission planning only; free-form natural-language planning is not established.",
            "The planner emits plans but executes no tools, network requests, writes, merges, or scientific promotions.",
            "Adaptive tool selection and dynamic multi-agent replanning remain separate unproven capabilities.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen bounded GAP-A02 unseen-mission planning benchmark.")
    parser.add_argument("--output", default="open-ended-planning-proof.json")
    parser.add_argument("--mission-json")
    args = parser.parse_args()

    if args.mission_json:
        mission = json.loads(args.mission_json)
        print(json.dumps(plan_mission(mission), sort_keys=True))
        return 0

    report = execute_benchmark((ROOT / args.output).resolve())
    print(json.dumps({"status": report["status"], "metrics": report["metrics"], "benchmark_fingerprint_sha256": report["benchmark_fingerprint_sha256"]}, sort_keys=True))
    return 0 if report["status"] == "OPEN_ENDED_PLANNING_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
