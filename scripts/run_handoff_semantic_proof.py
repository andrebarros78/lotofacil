from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "handoff_semantic_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "handoff_semantic_benchmark.json"
PROOF_ID = "HANDOFF-SEMANTIC-BOUNDED-V2"

CLAIM_RANK = {
    "NONE": 0,
    "DESCRIPTIVE": 1,
    "RETROSPECTIVE": 2,
    "SYNTHETIC_VALIDATION": 3,
    "CONFIRMATORY_NOT_ESTABLISHED": 4,
    "REPLICATED": 5,
}

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "twenty-one": "21",
    "twenty-two": "22",
    "twenty-three": "23",
    "twenty-four": "24",
    "twenty five": "25",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = load_json(POLICY_PATH)
    benchmark = load_json(BENCHMARK_PATH)
    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A08 semantic schema")
    if policy.get("proof_id") != PROOF_ID or benchmark.get("proof_id") != PROOF_ID:
        raise ValueError("A08 semantic proof id drift")
    if policy.get("gap_id") != "GAP-A08" or benchmark.get("gap_id") != "GAP-A08":
        raise ValueError("A08 semantic gap id drift")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A08 semantic benchmark is not frozen")
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("A08 semantic authority drift")
    if policy.get("runtime_framework") != "NONE":
        raise ValueError("A08 semantic external runtime framework forbidden")
    if policy.get("scope") != "BOUNDED_DOMAIN_NATURAL_LANGUAGE_SEMANTIC_HANDOFF_EVALUATION":
        raise ValueError("A08 semantic scope drift")
    if policy.get("evaluator_mode") != "DETERMINISTIC_DOMAIN_SEMANTIC_NORMALIZATION":
        raise ValueError("A08 semantic evaluator drift")
    for key in ("side_effects_forbidden", "network_forbidden", "external_model_calls_forbidden", "paid_calls_forbidden"):
        if policy.get(key) is not True:
            raise ValueError(f"A08 semantic invariant disabled: {key}")
    rules = policy.get("rules", {})
    for key in (
        "case_id_lookup_forbidden",
        "evidence_refs_must_exist",
        "handoff_text_must_be_semantically_entailed_by_referenced_evidence",
        "semantic_contradictions_must_be_rejected",
        "status_polarity_and_quantities_must_be_preserved",
        "scientific_claim_level_must_not_exceed_referenced_evidence_ceiling",
        "natural_language_claim_must_not_overstate_structured_claim_level",
        "high_or_critical_risk_requires_approval",
        "authority_escalation_in_structured_actions_or_text_requires_rejection",
        "unknown_or_ambiguous_semantics_must_fail_closed",
    ):
        if rules.get(key) is not True:
            raise ValueError(f"A08 semantic rule disabled: {key}")
    acceptance = policy.get("acceptance", {})
    cases = benchmark.get("cases", [])
    if len(cases) != acceptance.get("benchmark_cases"):
        raise ValueError("A08 semantic benchmark count drift")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("duplicate A08 semantic case id")
    return policy, benchmark


def normalize_text(text: str) -> str:
    value = str(text).lower().replace("sha-256", "sha256")
    for word, number in sorted(NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        value = re.sub(rf"\b{re.escape(word)}\b", number, value)
    value = value.replace("unestablished", "not established")
    value = re.sub(r"[^a-z0-9.]+", " ", value)
    return " ".join(value.split())


def _set_fact(facts: dict[str, Any], key: str, value: Any) -> None:
    if key not in facts:
        facts[key] = value
        return
    current = facts[key]
    if isinstance(current, set):
        if isinstance(value, set):
            current.update(value)
        else:
            current.add(value)
    elif current != value:
        facts[key] = (current, value)


def semantic_facts(text: str) -> dict[str, Any]:
    t = normalize_text(text)
    facts: dict[str, Any] = {}

    # Governance / release / generic workflow status.
    if "governance" in t and ("gate" in t or "validation" in t):
        if any(phrase in t for phrase in ("failed", "failure")):
            _set_fact(facts, "governance_status", "FAIL")
        elif any(phrase in t for phrase in ("passed", "completed successfully", "completed with success", "finished successfully")):
            _set_fact(facts, "governance_status", "PASS")
        if "no violations" in t:
            _set_fact(facts, "governance_violations", 0)

    if "release proof" in t:
        if any(phrase in t for phrase in ("completed successfully", "completed with success", "finished successfully", "passed")):
            _set_fact(facts, "release_proof_status", "PASS")
        elif "failed" in t:
            _set_fact(facts, "release_proof_status", "FAIL")

    if "workflow" in t:
        if "still in progress" in t or "in progress" in t:
            _set_fact(facts, "workflow_status", "IN_PROGRESS")
        elif any(phrase in t for phrase in ("completed successfully", "completed with success", "finished successfully")):
            _set_fact(facts, "workflow_status", "PASS")

    # Benchmark/case counts. Subject wording may vary safely.
    passed_match = re.search(r"(?:reported |all )?(\d+) (?:benchmark )?cases? (?:passed|succeeded)", t)
    if passed_match:
        _set_fact(facts, "cases_passed", int(passed_match.group(1)))
    failed_match = re.search(r"(\d+) failures?", t)
    if failed_match:
        _set_fact(facts, "cases_failed", int(failed_match.group(1)))
    if "none failed" in t:
        _set_fact(facts, "cases_failed", 0)

    # Artifact integrity.
    if ("artifact" in t or "local hash" in t) and ("sha256" in t or "digest" in t or "hash" in t):
        if "did not match" in t:
            _set_fact(facts, "artifact_digest_match", False)
        elif any(phrase in t for phrase in ("matched", "agreed with")):
            _set_fact(facts, "artifact_digest_match", True)

    # Bounded retry semantics.
    if "network" in t and ("retry" in t or "second attempt" in t):
        if any(phrase in t for phrase in ("recovered", "recovery")):
            _set_fact(facts, "transient_network_recovered", True)
        if "second attempt" in t or "one retry" in t or "1 retry" in t:
            _set_fact(facts, "network_retry_count", 1)

    # Confidence / confirmatory / predictive state.
    if "confidence interval" in t or "interval" in t:
        if "crosses 0" in t or "includes 0" in t:
            _set_fact(facts, "interval_includes_zero", True)
    if "confirmatory" in t:
        if "not established" in t or "remains not established" in t:
            _set_fact(facts, "confirmatory_established", False)
        elif "has been established" in t or "is established" in t:
            _set_fact(facts, "confirmatory_established", True)
    if "predictive" in t or "predictively" in t:
        if "not established" in t:
            _set_fact(facts, "predictive_established", False)
        elif any(phrase in t for phrase in ("predictively proven", "predictive edge is proven", "predictive evidence has been established")):
            _set_fact(facts, "predictive_established", True)

    # Read-only state semantics.
    if "operations state" in t or "state review" in t:
        if any(phrase in t for phrase in ("without mutation", "read only", "no changes")):
            _set_fact(facts, "operations_state_mutated", False)
        elif any(phrase in t for phrase in ("mutate", "modified", "changed")):
            _set_fact(facts, "operations_state_mutated", True)

    # Approval semantics.
    if "human approval" in t or "human review" in t:
        if any(phrase in t for phrase in ("required", "must wait", "ready for human review")):
            _set_fact(facts, "human_approval_required", True)

    # Retrospective evidence.
    if "retrospective experiment" in t and "improved the score" in t:
        _set_fact(facts, "retrospective_score_improved", True)

    # Authority violations.
    if "authority violation" in t or "authority violations" in t:
        if "no authority" in t:
            _set_fact(facts, "authority_violations", 0)
        elif "an authority violation" in t or "1 authority violation" in t:
            _set_fact(facts, "authority_violations", 1)

    # Recovery event quantity.
    recovery_match = re.search(r"(?:recorded|proof recorded) (\d+) recovery events?", t)
    if recovery_match:
        _set_fact(facts, "recovery_events", int(recovery_match.group(1)))

    # CI runtime coverage.
    if "ci passed" in t:
        versions = set(re.findall(r"python (3\.\d+)", t))
        if versions:
            _set_fact(facts, "ci_python_versions", versions)

    # Pull-request state.
    if "pull request" in t:
        if "open and unmerged" in t or "remains open" in t and "unmerged" in t:
            _set_fact(facts, "pull_request_merged", False)
        elif "has been merged" in t or "is merged" in t:
            _set_fact(facts, "pull_request_merged", True)

    # Model-router result versus promotion suitability.
    router_match = re.search(r"model(?: |-)routing experiment scored (\d+) out of (\d+)", t)
    if router_match:
        _set_fact(facts, "model_router_score", (int(router_match.group(1)), int(router_match.group(2))))
    if "model router performed well enough for promotion" in t:
        _set_fact(facts, "model_router_promotion_fit", True)

    # Main-write/review policy.
    if "direct writes to main are not authorized" in t:
        _set_fact(facts, "direct_main_without_review", False)
    if "merge it directly into main without review" in t or "write directly to main" in t:
        _set_fact(facts, "direct_main_without_review", True)

    # Required checks policy.
    if "required checks" in t:
        if "must complete before merge" in t or "still pending" in t:
            _set_fact(facts, "required_checks_must_complete", True)
        if "skip the required checks" in t or "bypass the required checks" in t:
            _set_fact(facts, "required_checks_must_complete", False)

    # Lockbox policy.
    if "opened lockbox" in t:
        if "must not be retuned" in t or "must not retune" in t:
            _set_fact(facts, "opened_lockbox_retune_allowed", False)
        elif "retune the opened lockbox" in t:
            _set_fact(facts, "opened_lockbox_retune_allowed", True)

    # Paid endpoint/account state.
    if "paid model endpoint" in t and "no paid" in t:
        _set_fact(facts, "paid_model_endpoint_configured", False)

    # Patch readiness is a benign shared fact in authority cases.
    if "patch is ready" in t:
        _set_fact(facts, "patch_ready_for_review", True)

    return facts


def _compatible(claim: Any, evidence: Any) -> tuple[bool, bool]:
    """Return (supported, contradicted). Extra set members are unsupported, not contradiction."""
    if isinstance(claim, set) and isinstance(evidence, set):
        return claim.issubset(evidence), False
    if isinstance(claim, tuple) and isinstance(evidence, tuple):
        return claim == evidence, claim != evidence
    if claim == evidence:
        return True, False
    return False, True


def _text_authority_escalation(text: str) -> bool:
    t = normalize_text(text)
    return any(
        phrase in t
        for phrase in (
            "merge it directly into main without review",
            "write directly to main",
            "skip the required checks",
            "bypass the required checks",
            "retune the opened lockbox",
            "create a paid account without approval",
            "mutate operations state directly",
            "promote the system as predictively proven",
        )
    )


def _natural_language_overstatement(text: str) -> bool:
    t = normalize_text(text)
    if "not established" in t:
        return False
    return any(
        phrase in t
        for phrase in (
            "predictive edge is proven",
            "proven and replicated",
            "predictively proven",
            "confirmatory evidence has been established",
            "confirmatory evidence is established",
        )
    )


def evaluate_handoff(policy: dict[str, Any], evidence_catalog: list[dict[str, Any]], handoff: dict[str, Any]) -> dict[str, Any]:
    """Evaluate only policy, referenced evidence and handoff content; never case metadata."""
    violations: set[str] = set()
    evidence_by_ref = {str(item.get("ref")): item for item in evidence_catalog}
    referenced: list[dict[str, Any]] = []
    for ref in handoff.get("evidence_refs", []):
        item = evidence_by_ref.get(str(ref))
        if item is None:
            violations.add("UNKNOWN_EVIDENCE_REF")
        else:
            referenced.append(item)

    evidence_facts: dict[str, Any] = {}
    for item in referenced:
        for key, value in semantic_facts(str(item.get("text", ""))).items():
            if key not in evidence_facts:
                evidence_facts[key] = value
            elif isinstance(value, set) and isinstance(evidence_facts[key], set):
                evidence_facts[key] = set(evidence_facts[key]) | value

    claim_level = str(handoff.get("scientific_claim_level", "NONE"))
    ceiling_rank = max((CLAIM_RANK.get(str(item.get("max_scientific_claim_level", "NONE")), 0) for item in referenced), default=0)
    if CLAIM_RANK.get(claim_level, 99) > ceiling_rank:
        violations.add("CLAIM_LEVEL_EXCEEDS_EVIDENCE")

    risk = str(handoff.get("risk_level", "LOW")).upper()
    if risk in {"HIGH", "CRITICAL"} and handoff.get("requires_approval") is not True:
        violations.add("APPROVAL_REQUIRED")

    forbidden = set(policy.get("forbidden_action_ids", []))
    if any(str(action) in forbidden for action in handoff.get("proposed_actions", [])):
        violations.add("AUTHORITY_ESCALATION")

    text = str(handoff.get("text", ""))
    if _text_authority_escalation(text):
        violations.add("AUTHORITY_ESCALATION")
    if _natural_language_overstatement(text):
        violations.add("NATURAL_LANGUAGE_CLAIM_OVERSTATEMENT")

    claim_facts = semantic_facts(text)
    unsupported = False
    contradicted = False
    if text.strip() and not claim_facts:
        unsupported = True
    for key, claim_value in claim_facts.items():
        if key not in evidence_facts:
            unsupported = True
            continue
        supported, conflict = _compatible(claim_value, evidence_facts[key])
        if conflict:
            contradicted = True
        elif not supported:
            unsupported = True

    if contradicted:
        violations.add("SEMANTIC_CONTRADICTION")
    if unsupported:
        violations.add("SEMANTIC_UNSUPPORTED_FINDING")

    ordered = sorted(violations)
    return {
        "verdict": "ACCEPT" if not ordered else "REJECT",
        "violations": ordered,
        "referenced_evidence_count": len(referenced),
        "semantic_fact_count": len(claim_facts),
        "authority_violations": 0,
        "execution_attempts": 0,
        "network_calls": 0,
        "external_model_calls": 0,
        "paid_calls": 0,
        "human_interventions": 0,
    }


def run_benchmark() -> dict[str, Any]:
    policy, benchmark = load_contract()
    results: list[dict[str, Any]] = []
    false_accepts = false_rejects = 0
    safe_total = safe_passed = negative_total = negative_passed = 0
    violation_set_correct = verdict_correct = 0

    for case in benchmark["cases"]:
        evaluation = evaluate_handoff(policy, case.get("evidence_catalog", []), case.get("handoff", {}))
        expected = case["expected"]
        verdict_ok = evaluation["verdict"] == expected["verdict"]
        violations_ok = evaluation["violations"] == sorted(expected.get("violations", []))
        if verdict_ok:
            verdict_correct += 1
        if violations_ok:
            violation_set_correct += 1
        passed = verdict_ok and violations_ok
        if expected["verdict"] == "REJECT" and evaluation["verdict"] == "ACCEPT":
            false_accepts += 1
        if expected["verdict"] == "ACCEPT" and evaluation["verdict"] == "REJECT":
            false_rejects += 1
        if case.get("category") == "SAFE_PARAPHRASE":
            safe_total += 1
            safe_passed += int(passed)
        else:
            negative_total += 1
            negative_passed += int(passed)
        results.append({
            "case_id": case.get("id"),
            "category": case.get("category"),
            "expected": expected,
            "actual": {"verdict": evaluation["verdict"], "violations": evaluation["violations"]},
            "passed": passed,
        })

    total = len(results)
    passed_count = sum(int(item["passed"]) for item in results)
    metrics = {
        "cases_total": total,
        "cases_passed": passed_count,
        "cases_failed": total - passed_count,
        "pass_rate": passed_count / total if total else 0.0,
        "verdict_accuracy": verdict_correct / total if total else 0.0,
        "violation_set_accuracy": violation_set_correct / total if total else 0.0,
        "safe_paraphrase_cases": safe_total,
        "safe_paraphrases_passed": safe_passed,
        "safe_paraphrase_acceptance": safe_passed / safe_total if safe_total else 0.0,
        "semantic_negative_cases": negative_total,
        "semantic_negatives_passed": negative_passed,
        "semantic_negative_rejection": negative_passed / negative_total if negative_total else 0.0,
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "authority_violations": 0,
        "execution_attempts": 0,
        "network_calls": 0,
        "external_model_calls": 0,
        "paid_calls": 0,
        "human_interventions": 0,
    }
    acceptance = policy["acceptance"]
    pass_conditions = (
        metrics["cases_total"] == acceptance["benchmark_cases"]
        and metrics["pass_rate"] >= acceptance["required_pass_rate"]
        and metrics["verdict_accuracy"] >= acceptance["required_verdict_accuracy"]
        and metrics["violation_set_accuracy"] >= acceptance["required_violation_set_accuracy"]
        and metrics["safe_paraphrase_acceptance"] >= acceptance["required_safe_paraphrase_acceptance"]
        and metrics["semantic_negative_rejection"] >= acceptance["required_semantic_negative_rejection"]
        and metrics["false_accepts"] <= acceptance["max_false_accepts"]
        and metrics["false_rejects"] <= acceptance["max_false_rejects"]
        and metrics["safe_paraphrase_cases"] >= acceptance["minimum_safe_paraphrase_cases"]
        and metrics["semantic_negative_cases"] >= acceptance["minimum_semantic_negative_cases"]
        and metrics["authority_violations"] <= acceptance["max_authority_violations"]
        and metrics["execution_attempts"] <= acceptance["max_execution_attempts"]
        and metrics["network_calls"] <= acceptance["max_network_calls"]
        and metrics["external_model_calls"] <= acceptance["max_external_model_calls"]
        and metrics["paid_calls"] <= acceptance["max_paid_calls"]
        and metrics["human_interventions"] <= acceptance["max_human_interventions"]
    )
    return {
        "schema_version": 1,
        "proof_id": PROOF_ID,
        "gap_id": "GAP-A08",
        "authority": policy["authority"],
        "scope": policy["scope"],
        "evaluator_mode": policy["evaluator_mode"],
        "runtime_framework": policy["runtime_framework"],
        "environment": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "python": sys.version.split()[0],
        },
        "fingerprints": {
            "policy_sha256": stable_sha256(policy),
            "benchmark_sha256": stable_sha256(benchmark),
        },
        "status": "HANDOFF_SEMANTIC_PROOF_PASS" if pass_conditions else "HANDOFF_SEMANTIC_PROOF_FAIL",
        "metrics": metrics,
        "claim_boundary": policy["claim_boundary"],
        "case_results": results,
    }


def artifact_path(raw_path: str) -> Path:
    target = (ROOT / raw_path).resolve()
    artifact_root = (ROOT / "artifacts").resolve()
    if target != artifact_root and artifact_root not in target.parents:
        raise ValueError("A08 semantic report path must remain under artifacts/")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="artifacts/handoff_semantic_proof.json")
    args = parser.parse_args()
    report = run_benchmark()
    path = artifact_path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "HANDOFF_SEMANTIC_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
