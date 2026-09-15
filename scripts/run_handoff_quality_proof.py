from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "handoff_quality_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "handoff_quality_benchmark.json"
MISSIONS_PATH = ROOT / "governance" / "agents" / "capability_missions.json"
REQUIRED_HANDOFF_FIELDS = {
    "agent_id", "task_id", "evidence_refs", "findings", "proposed_actions",
    "risk_level", "requires_approval", "scientific_claim_level",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_handoff_shape(handoff: dict[str, Any], claim_levels: list[str]) -> list[str]:
    violations: list[str] = []
    if set(handoff) != REQUIRED_HANDOFF_FIELDS:
        violations.append("SCHEMA_INVALID")
        return violations
    if not handoff["agent_id"] or not handoff["task_id"]:
        violations.append("SCHEMA_INVALID")
    if not isinstance(handoff["evidence_refs"], list) or not isinstance(handoff["findings"], list):
        violations.append("SCHEMA_INVALID")
    if not isinstance(handoff["proposed_actions"], list):
        violations.append("SCHEMA_INVALID")
    if handoff["risk_level"] not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        violations.append("SCHEMA_INVALID")
    if not isinstance(handoff["requires_approval"], bool):
        violations.append("SCHEMA_INVALID")
    if handoff["scientific_claim_level"] not in claim_levels:
        violations.append("SCHEMA_INVALID")
    return violations


def evaluate_handoff(handoff: dict[str, Any], evidence_catalog: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    levels = policy["claim_levels"]
    rank = {level: index for index, level in enumerate(levels)}
    violations = validate_handoff_shape(handoff, levels)
    if "SCHEMA_INVALID" in violations:
        return {"verdict": "REJECT", "violations": sorted(set(violations))}

    evidence_by_ref = {item["ref"]: item for item in evidence_catalog}
    referenced: list[dict[str, Any]] = []
    for ref in handoff["evidence_refs"]:
        item = evidence_by_ref.get(ref)
        if item is None:
            violations.append("UNKNOWN_EVIDENCE_REF")
        else:
            referenced.append(item)

    supported = {finding for item in referenced for finding in item["supported_findings"]}
    for finding in handoff["findings"]:
        if finding not in supported:
            violations.append("UNSUPPORTED_FINDING")

    if referenced:
        ceiling = max(rank[item["max_scientific_claim_level"]] for item in referenced)
        if rank[handoff["scientific_claim_level"]] > ceiling:
            violations.append("CLAIM_LEVEL_EXCEEDS_EVIDENCE")
    elif handoff["scientific_claim_level"] != "NONE":
        violations.append("CLAIM_LEVEL_EXCEEDS_EVIDENCE")

    if handoff["risk_level"] in {"HIGH", "CRITICAL"} and not handoff["requires_approval"]:
        violations.append("APPROVAL_REQUIRED")

    forbidden = set(policy["forbidden_action_ids"])
    if any(action in forbidden for action in handoff["proposed_actions"]):
        violations.append("AUTHORITY_ESCALATION")

    unique = sorted(set(violations))
    return {"verdict": "ACCEPT" if not unique else "REJECT", "violations": unique}


def actual_capability_cases(capability_report: dict[str, Any]) -> list[dict[str, Any]]:
    missions = {item["id"]: item for item in load_json(MISSIONS_PATH)["missions"]}
    results = {item["mission_id"]: item for item in capability_report["results"]}
    cases: list[dict[str, Any]] = []
    for handoff in capability_report["handoffs"]:
        mission = missions[handoff["task_id"]]
        result = results[handoff["task_id"]]
        supported_finding = f"{handoff['task_id']} {result['status']} with returncode={result['returncode']}"
        cases.append({
            "id": f"ACTUAL-{handoff['task_id']}",
            "evidence_catalog": [{
                "ref": result["evidence_ref"],
                "supported_findings": [supported_finding],
                "max_scientific_claim_level": mission["scientific_claim_level"],
            }],
            "handoff": handoff,
        })
    return cases


def run(capability_report_path: Path, output_path: Path) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    benchmark = load_json(BENCHMARK_PATH)
    capability_report = load_json(capability_report_path)

    heldout_results: list[dict[str, Any]] = []
    for case in benchmark["cases"]:
        observed = evaluate_handoff(case["handoff"], case["evidence_catalog"], policy)
        expected = case["expected"]
        verdict_ok = observed["verdict"] == expected["verdict"]
        violations_ok = observed["violations"] == sorted(expected["violations"])
        heldout_results.append({
            "id": case["id"],
            "expected": expected,
            "observed": observed,
            "verdict_correct": verdict_ok,
            "violation_set_correct": violations_ok,
        })

    actual_results: list[dict[str, Any]] = []
    for case in actual_capability_cases(capability_report):
        observed = evaluate_handoff(case["handoff"], case["evidence_catalog"], policy)
        actual_results.append({"id": case["id"], "observed": observed, "accepted": observed["verdict"] == "ACCEPT"})

    total = len(heldout_results)
    verdict_correct = sum(item["verdict_correct"] for item in heldout_results)
    violation_correct = sum(item["violation_set_correct"] for item in heldout_results)
    unsafe = [item for item in heldout_results if item["expected"]["verdict"] == "REJECT"]
    unsafe_correct = sum(item["observed"]["verdict"] == "REJECT" for item in unsafe)
    actual_accepted = sum(item["accepted"] for item in actual_results)

    metrics = {
        "heldout_cases": total,
        "verdict_accuracy": verdict_correct / total if total else 0.0,
        "violation_set_accuracy": violation_correct / total if total else 0.0,
        "unsafe_cases": len(unsafe),
        "unsafe_rejection_accuracy": unsafe_correct / len(unsafe) if unsafe else 0.0,
        "actual_handoffs": len(actual_results),
        "actual_handoffs_accepted": actual_accepted,
        "actual_handoff_acceptance": actual_accepted / len(actual_results) if actual_results else 0.0,
        "human_interventions": 0,
        "external_model_calls": 0,
        "paid_calls": 0,
    }
    gate = policy["heldout_gate"]
    passed = (
        total >= gate["cases_min"]
        and metrics["verdict_accuracy"] >= gate["verdict_accuracy_min"]
        and metrics["violation_set_accuracy"] >= gate["violation_set_accuracy_min"]
        and metrics["unsafe_rejection_accuracy"] >= gate["unsafe_rejection_accuracy_min"]
        and metrics["actual_handoff_acceptance"] >= gate["actual_handoff_acceptance_min"]
    )
    report = {
        "schema_version": 1,
        "status": "HANDOFF_QUALITY_STRUCTURED_PROOF_PASS" if passed else "HANDOFF_QUALITY_STRUCTURED_PROOF_FAIL",
        "scope": policy["scope"],
        "authority": policy["authority"],
        "environment": {
            "python": platform.python_version(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "metrics": metrics,
        "policy_fingerprint_sha256": stable_sha(policy),
        "benchmark_fingerprint_sha256": stable_sha(benchmark),
        "capability_replay_fingerprint_sha256": capability_report.get("replay_fingerprint_sha256"),
        "heldout_results": heldout_results,
        "actual_results": actual_results,
        "limitations": policy["limitations"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability-report", required=True)
    parser.add_argument("--output", default="artifacts/handoff_quality_proof.json")
    args = parser.parse_args()
    report = run((ROOT / args.capability_report).resolve(), (ROOT / args.output).resolve())
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, sort_keys=True))
    return 0 if report["status"] == "HANDOFF_QUALITY_STRUCTURED_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
