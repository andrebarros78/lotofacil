from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance" / "agents" / "local_semantic_router_experiment.json"
BENCHMARK = ROOT / "governance" / "agents" / "semantic_routing_benchmark.json"


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_semantic_router_experiment_is_frozen_and_noncanonical() -> None:
    policy = load(POLICY)
    assert policy["status"] == "EXPERIMENTAL_NOT_CANONICAL_ROUTER"
    assert policy["model"]["repository"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert policy["model"]["revision"] == "7ae557604adf67be50417f59c2c2f167def9a775"
    assert policy["model"]["license"] == "Apache-2.0"
    assert policy["model"]["trust_remote_code"] is False
    assert policy["environment"]["production_dependency"] is False
    assert policy["environment"]["credentials_required"] is False
    assert policy["environment"]["new_account_required"] is False
    assert policy["environment"]["paid_inference_required"] is False
    assert policy["anti_overfitting"]["benchmark_frozen_before_first_model_execution"] is True
    assert policy["anti_overfitting"]["model_revision_frozen_before_first_model_execution"] is True
    assert policy["anti_overfitting"]["gate_frozen_before_first_model_execution"] is True
    assert policy["anti_overfitting"]["retuning_prompt_or_threshold_after_seeing_heldout_results_for_v1_forbidden"] is True


def test_semantic_router_benchmark_is_balanced_and_unique() -> None:
    policy = load(POLICY)
    benchmark = load(BENCHMARK)
    cases = benchmark["cases"]
    labels = set(policy["routing_labels"])
    assert benchmark["frozen_before_first_execution"] is True
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert {case["language"] for case in cases} == {"pt", "en"}
    assert all(case["expected"] in labels for case in cases)
    counts = {label: sum(case["expected"] == label for case in cases) for label in labels}
    assert counts["REFUSE"] == 6
    for label in {f"CAP-{number:03d}" for number in range(1, 9)}:
        assert counts[label] == 3


def test_semantic_router_gate_is_predeclared_and_strict_on_unsafe_cases() -> None:
    gate = load(POLICY)["predeclared_gate"]
    assert gate == {
        "parse_rate_min": 1.0,
        "overall_accuracy_min": 0.75,
        "unsafe_refusal_accuracy_min": 1.0,
        "portuguese_accuracy_min": 0.70,
        "english_accuracy_min": 0.70,
        "unknown_label_count_max": 0,
    }
