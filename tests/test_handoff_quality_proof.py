from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_handoff_quality_proof.py"
SPEC = importlib.util.spec_from_file_location("handoff_quality_proof", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_json(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_frozen_handoff_benchmark_is_nontrivial_and_balanced_for_failure_modes() -> None:
    policy = load_json("governance/agents/handoff_quality_policy.json")
    benchmark = load_json("governance/agents/handoff_quality_benchmark.json")
    assert policy["scope"] == "STRUCTURED_HANDOFF_EVALUATION_ONLY"
    assert len(benchmark["cases"]) == 16
    assert len({case["id"] for case in benchmark["cases"]}) == 16
    assert sum(case["expected"]["verdict"] == "ACCEPT" for case in benchmark["cases"]) == 4
    assert sum(case["expected"]["verdict"] == "REJECT" for case in benchmark["cases"]) == 12
    expected_violations = {v for case in benchmark["cases"] for v in case["expected"]["violations"]}
    assert {"UNKNOWN_EVIDENCE_REF", "UNSUPPORTED_FINDING", "CLAIM_LEVEL_EXCEEDS_EVIDENCE", "APPROVAL_REQUIRED", "AUTHORITY_ESCALATION"} <= expected_violations


def test_evaluator_reproduces_every_frozen_expected_verdict_and_violation_set() -> None:
    policy = load_json("governance/agents/handoff_quality_policy.json")
    benchmark = load_json("governance/agents/handoff_quality_benchmark.json")
    for case in benchmark["cases"]:
        observed = MODULE.evaluate_handoff(case["handoff"], case["evidence_catalog"], policy)
        assert observed["verdict"] == case["expected"]["verdict"], case["id"]
        assert observed["violations"] == sorted(case["expected"]["violations"]), case["id"]


def test_policy_does_not_claim_free_form_semantic_entailment() -> None:
    policy = load_json("governance/agents/handoff_quality_policy.json")
    text = " ".join(policy["limitations"])
    assert "does not establish free-form natural-language semantic entailment" in text
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["heldout_gate"]["verdict_accuracy_min"] == 1.0
    assert policy["heldout_gate"]["violation_set_accuracy_min"] == 1.0
