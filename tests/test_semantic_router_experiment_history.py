from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_rejected_semantic_router_v1_is_recorded_without_promoting_gap() -> None:
    history = load_json("governance/agents/semantic_router_experiment_history.json")
    record = history["experiments"][0]
    assert record["experiment_id"] == "LOCAL-SEMANTIC-ROUTER-QWEN25-05B-V1"
    assert record["decision"] == "REJECTED"
    assert record["observed_metrics"]["cases_correct"] == 3
    assert record["observed_metrics"]["cases_total"] == 30
    assert record["observed_metrics"]["overall_accuracy"] == 0.1
    assert record["observed_metrics"]["unsafe_refusal_accuracy"] == 0.0
    assert record["observed_metrics"]["parse_rate"] == 1.0
    assert record["evidence"]["artifact_id"] == 10413853724
    assert record["governance_effect"]["promoted_to_runtime"] is False
    assert record["governance_effect"]["prompt_retuned_after_result"] is False
    assert record["governance_effect"]["benchmark_retuned_after_result"] is False

    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A03"]["status"] == "NOT_PROVEN"
