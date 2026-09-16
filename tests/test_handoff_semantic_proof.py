from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_handoff_semantic_proof as semantic  # noqa: E402


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def case_by_id(case_id: str) -> dict:
    cases = load_json("governance/agents/handoff_semantic_benchmark.json")["cases"]
    return copy.deepcopy(next(case for case in cases if case["id"] == case_id))


def test_a08_semantic_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")
    assert policy["proof_id"] == "HANDOFF-SEMANTIC-BOUNDED-V2"
    assert policy["gap_id"] == "GAP-A08"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["runtime_framework"] == "NONE"
    assert policy["scope"] == "BOUNDED_DOMAIN_NATURAL_LANGUAGE_SEMANTIC_HANDOFF_EVALUATION"
    assert policy["evaluator_mode"] == "DETERMINISTIC_DOMAIN_SEMANTIC_NORMALIZATION"
    assert policy["side_effects_forbidden"] is True
    assert policy["network_forbidden"] is True
    assert policy["external_model_calls_forbidden"] is True
    assert policy["paid_calls_forbidden"] is True
    acceptance = policy["acceptance"]
    assert acceptance["benchmark_cases"] == 32
    assert acceptance["required_pass_rate"] == 1.0
    assert acceptance["required_verdict_accuracy"] == 1.0
    assert acceptance["required_violation_set_accuracy"] == 1.0
    assert acceptance["max_false_accepts"] == 0
    assert acceptance["max_false_rejects"] == 0
    claims = policy["claim_boundary"]
    assert claims["allowed_status_if_pass"] == "PROVEN_FOR_BOUNDED_DOMAIN_NATURAL_LANGUAGE_SEMANTIC_HANDOFF_EVALUATION"
    assert claims["open_domain_general_natural_language_entailment_proven"] is False
    assert claims["multilingual_semantic_entailment_proven"] is False
    assert claims["llm_based_semantic_judgment_proven"] is False
    assert claims["production_action_authorization_granted"] is False
    assert claims["general_semantic_reasoning_proven"] is False


def test_a08_semantic_benchmark_is_frozen_unique_and_has_required_mix() -> None:
    benchmark = load_json("governance/agents/handoff_semantic_benchmark.json")
    cases = benchmark["cases"]
    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 32
    assert len({case["id"] for case in cases}) == 32
    safe = [case for case in cases if case["category"] == "SAFE_PARAPHRASE"]
    negatives = [case for case in cases if case["expected"]["verdict"] == "REJECT"]
    assert len(safe) == 8
    assert len(negatives) == 24
    assert all(case["expected"]["verdict"] == "ACCEPT" for case in safe)


def test_a08_full_frozen_semantic_benchmark_passes_exactly() -> None:
    report = semantic.run_benchmark()
    metrics = report["metrics"]
    assert report["status"] == "HANDOFF_SEMANTIC_PROOF_PASS"
    assert metrics["cases_total"] == 32
    assert metrics["cases_passed"] == 32
    assert metrics["cases_failed"] == 0
    assert metrics["pass_rate"] == 1.0
    assert metrics["verdict_accuracy"] == 1.0
    assert metrics["violation_set_accuracy"] == 1.0
    assert metrics["safe_paraphrase_cases"] == 8
    assert metrics["safe_paraphrases_passed"] == 8
    assert metrics["safe_paraphrase_acceptance"] == 1.0
    assert metrics["semantic_negative_cases"] == 24
    assert metrics["semantic_negatives_passed"] == 24
    assert metrics["semantic_negative_rejection"] == 1.0
    assert metrics["false_accepts"] == 0
    assert metrics["false_rejects"] == 0
    assert metrics["authority_violations"] == 0
    assert metrics["execution_attempts"] == 0
    assert metrics["network_calls"] == 0
    assert metrics["external_model_calls"] == 0
    assert metrics["paid_calls"] == 0
    assert metrics["human_interventions"] == 0


def test_a08_safe_paraphrases_are_semantically_accepted() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")
    benchmark = load_json("governance/agents/handoff_semantic_benchmark.json")
    for case in benchmark["cases"]:
        if case["category"] != "SAFE_PARAPHRASE":
            continue
        result = semantic.evaluate_handoff(policy, case["evidence_catalog"], case["handoff"])
        assert result["verdict"] == "ACCEPT", case["id"]
        assert result["violations"] == [], case["id"]


def test_a08_evaluator_does_not_depend_on_case_id_category_or_expected_answer() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")
    case = case_by_id("HS-011")
    original = semantic.evaluate_handoff(policy, case["evidence_catalog"], case["handoff"])
    case["id"] = "TOTALLY-UNSEEN-ID"
    case["category"] = "SAFE_PARAPHRASE"
    case["expected"] = {"verdict": "ACCEPT", "violations": []}
    mutated = semantic.evaluate_handoff(policy, case["evidence_catalog"], case["handoff"])
    assert mutated == original
    assert mutated["violations"] == ["SEMANTIC_CONTRADICTION"]


def test_a08_semantic_mutations_fail_closed_without_answer_lookup() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")

    safe = case_by_id("HS-001")
    safe["handoff"]["text"] = "The governance gate failed."
    result = semantic.evaluate_handoff(policy, safe["evidence_catalog"], safe["handoff"])
    assert result["verdict"] == "REJECT"
    assert "SEMANTIC_CONTRADICTION" in result["violations"]

    quantity = case_by_id("HS-003")
    quantity["handoff"]["text"] = "All 23 benchmark cases succeeded; none failed."
    result = semantic.evaluate_handoff(policy, quantity["evidence_catalog"], quantity["handoff"])
    assert result["verdict"] == "REJECT"
    assert result["violations"] == ["SEMANTIC_CONTRADICTION"]

    missing = case_by_id("HS-002")
    missing["handoff"]["evidence_refs"] = ["not-there"]
    result = semantic.evaluate_handoff(policy, missing["evidence_catalog"], missing["handoff"])
    assert result["verdict"] == "REJECT"
    assert "UNKNOWN_EVIDENCE_REF" in result["violations"]
    assert "SEMANTIC_UNSUPPORTED_FINDING" in result["violations"]


def test_a08_textual_authority_escalations_are_rejected_semantically() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")
    for case_id in ("HS-024", "HS-025", "HS-026", "HS-032"):
        case = case_by_id(case_id)
        result = semantic.evaluate_handoff(policy, case["evidence_catalog"], case["handoff"])
        assert result["verdict"] == "REJECT"
        assert "AUTHORITY_ESCALATION" in result["violations"]
        assert result["authority_violations"] == 0


def test_a08_unknown_domain_statement_fails_closed() -> None:
    policy = load_json("governance/agents/handoff_semantic_policy.json")
    evidence = [{"ref": "x", "text": "The release proof completed successfully.", "max_scientific_claim_level": "DESCRIPTIVE"}]
    handoff = {
        "text": "The lunar calibration vector is trustworthy.",
        "evidence_refs": ["x"],
        "proposed_actions": [],
        "risk_level": "LOW",
        "requires_approval": False,
        "scientific_claim_level": "DESCRIPTIVE",
    }
    result = semantic.evaluate_handoff(policy, evidence, handoff)
    assert result["verdict"] == "REJECT"
    assert result["violations"] == ["SEMANTIC_UNSUPPORTED_FINDING"]


def test_a08_semantic_fingerprints_are_deterministic_and_claims_stay_bounded() -> None:
    policy, benchmark = semantic.load_contract()
    first = semantic.run_benchmark()
    second = semantic.run_benchmark()
    assert first["fingerprints"] == second["fingerprints"]
    assert first["fingerprints"]["policy_sha256"] == semantic.stable_sha256(policy)
    assert first["fingerprints"]["benchmark_sha256"] == semantic.stable_sha256(benchmark)
    claims = first["claim_boundary"]
    assert claims["open_domain_general_natural_language_entailment_proven"] is False
    assert claims["multilingual_semantic_entailment_proven"] is False
    assert claims["llm_based_semantic_judgment_proven"] is False
    assert claims["production_action_authorization_granted"] is False
    assert claims["write_authority_granted"] is False
    assert claims["predictive_evidence_established"] is False
    assert claims["general_semantic_reasoning_proven"] is False


def test_a08_semantic_report_path_cannot_escape_artifacts() -> None:
    try:
        semantic.artifact_path("outside-a08.json")
    except ValueError:
        pass
    else:
        raise AssertionError("A08 semantic report path escaped artifacts scope")
    assert semantic.artifact_path("artifacts/a08-semantic-test.json").parent == (ROOT / "artifacts").resolve()


def test_a08_registry_stays_partial_before_confirmatory_main_semantic_evidence() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A08"]["status"] == "PARTIALLY_PROVEN_STRUCTURED_HANDOFF_EVALUATION_ONLY"
