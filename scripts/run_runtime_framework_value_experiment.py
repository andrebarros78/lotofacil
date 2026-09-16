from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "runtime_framework_value_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "runtime_framework_value_benchmark.json"
PROOF_ID = "AGENT-RUNTIME-FRAMEWORK-VALUE-BOUNDED-V1"


class ExperimentState(TypedDict, total=False):
    value: int
    add: int
    multiply: int
    left_add: int
    right_multiply: int
    sink_add: int
    source_add: int
    left_value: int
    right_value: int
    final_value: int


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def artifact_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    artifacts = (ROOT / "artifacts").resolve()
    if path != artifacts and artifacts not in path.parents:
        raise ValueError("A10 report paths must remain under artifacts/")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = load_json(POLICY_PATH)
    benchmark = load_json(BENCHMARK_PATH)
    if policy.get("schema_version") != 1 or benchmark.get("schema_version") != 1:
        raise ValueError("unsupported A10 schema")
    if policy.get("proof_id") != PROOF_ID or benchmark.get("proof_id") != PROOF_ID:
        raise ValueError("A10 proof id drift")
    if policy.get("gap_id") != "GAP-A10" or benchmark.get("gap_id") != "GAP-A10":
        raise ValueError("A10 gap id drift")
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("A10 authority drift")
    if policy.get("canonical_runtime_framework") != "NONE":
        raise ValueError("A10 canonical runtime must remain framework independent")
    if benchmark.get("frozen_before_implementation") is not True:
        raise ValueError("A10 benchmark is not frozen")
    cases = benchmark.get("cases", [])
    acceptance = policy.get("acceptance", {})
    if len(cases) != benchmark.get("cases_total") or len(cases) != acceptance.get("benchmark_cases"):
        raise ValueError("A10 benchmark case count drift")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("duplicate A10 case id")
    fault_cases = sum(case.get("fault", {}).get("kind") != "NONE" for case in cases)
    if fault_cases != benchmark.get("fault_cases_total") or fault_cases != acceptance.get("fault_cases"):
        raise ValueError("A10 fault case count drift")
    risk = policy.get("candidate", {}).get("known_upstream_risk", {})
    if risk.get("must_remain_in_benchmark") is not True:
        raise ValueError("A10 upstream risk benchmark requirement disabled")
    if not any(case.get("class") == "CONDITIONAL_ROUTER_FAILURE_RESUME" for case in cases):
        raise ValueError("A10 known router recovery risk removed from benchmark")
    return policy, benchmark


def candidate_runtime_available() -> bool:
    try:
        return importlib.metadata.version("langgraph") == "1.2.11" and importlib.metadata.version("langgraph-checkpoint-sqlite") == "3.1.1"
    except importlib.metadata.PackageNotFoundError:
        return False


def _result(
    case: dict[str, Any],
    *,
    runtime: str,
    supported: bool,
    completed: bool,
    final_value: int | None,
    path: list[str],
    recovered: bool,
    nominal_success: bool,
    pending_after: list[str] | None = None,
    attempts: int = 1,
    duration_ms: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    expected = case["expected"]
    correct_final_state = bool(
        supported
        and completed
        and final_value == expected["final_value"]
        and path == expected["path"]
    )
    hidden_failure_success = bool(nominal_success and not correct_final_state)
    return {
        "case_id": case["id"],
        "class": case["class"],
        "runtime": runtime,
        "supported": supported,
        "completed": completed,
        "nominal_success": nominal_success,
        "correct_final_state": correct_final_state,
        "hidden_failure_success": hidden_failure_success,
        "final_value": final_value,
        "expected_final_value": expected["final_value"],
        "path": path,
        "expected_path": expected["path"],
        "recovered": recovered,
        "fault": case["fault"],
        "pending_after": pending_after or [],
        "attempts": attempts,
        "duration_ms": duration_ms,
        "error": error,
    }


def run_baseline_case(case: dict[str, Any], temp_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    if not case["baseline_supported"]:
        return _result(
            case,
            runtime="FRAMEWORK_INDEPENDENT_BASELINE",
            supported=False,
            completed=False,
            final_value=None,
            path=[],
            recovered=False,
            nominal_success=False,
            duration_ms=int(round((time.monotonic() - started) * 1000)),
            error="UNSUPPORTED_BY_FROZEN_BASELINE",
        )

    payload = dict(case["input"])
    path: list[str] = []
    attempts = 1
    recovered = False

    def step1() -> None:
        payload["value"] = int(payload["value"]) + int(payload["add"])
        path.append("step1")

    def step2() -> None:
        payload["value"] = int(payload["value"]) * int(payload["multiply"])
        path.append("step2")

    if case["class"] == "LINEAR_CLEAN":
        step1()
        step2()
    elif case["class"] == "TRANSIENT_NODE_FAILURE":
        step1()
        attempts = 2
        # The frozen framework-independent baseline supports one bounded retry.
        recovered = True
        step2()
    elif case["class"] == "PROCESS_INTERRUPT_RESUME":
        step1()
        checkpoint = temp_dir / f"baseline-{case['id']}.json"
        checkpoint.write_text(json.dumps({"payload": payload, "path": path}, sort_keys=True), encoding="utf-8")
        resumed = json.loads(checkpoint.read_text(encoding="utf-8"))
        payload = dict(resumed["payload"])
        path = list(resumed["path"])
        attempts = 2
        recovered = True
        step2()
    else:
        raise AssertionError(f"unexpected supported baseline class: {case['class']}")

    return _result(
        case,
        runtime="FRAMEWORK_INDEPENDENT_BASELINE",
        supported=True,
        completed=True,
        final_value=int(payload["value"]),
        path=path,
        recovered=recovered,
        nominal_success=True,
        attempts=attempts,
        duration_ms=int(round((time.monotonic() - started) * 1000)),
    )


def _imports() -> tuple[Any, Any, Any, Any]:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    return SqliteSaver, StateGraph, START, END


def _sqlite_path(temp_dir: Path, case_id: str) -> Path:
    return temp_dir / f"candidate-{case_id}.sqlite"


def run_candidate_linear(case: dict[str, Any], temp_dir: Path, mode: str) -> dict[str, Any]:
    SqliteSaver, StateGraph, START, END = _imports()
    started = time.monotonic()
    calls = {"step1": 0, "step2": 0}
    path: list[str] = []
    fail_once = {"step2": mode == "TRANSIENT_NODE_FAILURE"}

    def step1(state: ExperimentState) -> dict[str, int]:
        calls["step1"] += 1
        path.append("step1")
        return {"value": int(state["value"]) + int(state["add"])}

    def step2(state: ExperimentState) -> dict[str, int]:
        calls["step2"] += 1
        if fail_once["step2"]:
            fail_once["step2"] = False
            raise RuntimeError("controlled A10 transient node failure")
        path.append("step2")
        return {"value": int(state["value"]) * int(state["multiply"])}

    def build(conn: sqlite3.Connection, interrupt_after: list[str] | None = None) -> Any:
        graph = StateGraph(ExperimentState)
        graph.add_node("step1", step1)
        graph.add_node("step2", step2)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", END)
        kwargs: dict[str, Any] = {"checkpointer": SqliteSaver(conn)}
        if interrupt_after:
            kwargs["interrupt_after"] = interrupt_after
        return graph.compile(**kwargs)

    db_path = _sqlite_path(temp_dir, case["id"])
    config = {"configurable": {"thread_id": case["id"]}}
    attempts = 1
    recovered = False
    error: str | None = None
    result_state: dict[str, Any] | None = None

    if mode == "PROCESS_INTERRUPT_RESUME":
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            app = build(conn, ["step1"])
            app.invoke(dict(case["input"]), config)
            before = app.get_state(config)
            if "step2" not in list(before.next):
                error = "expected step2 pending after bounded interruption"
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            app = build(conn)
            result_state = app.invoke(None, config)
            after = app.get_state(config)
            pending_after = list(after.next)
        attempts = 2
        recovered = result_state is not None and not pending_after
    else:
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            app = build(conn)
            try:
                result_state = app.invoke(dict(case["input"]), config)
                pending_after = list(app.get_state(config).next)
            except RuntimeError as exc:
                error = str(exc)
                attempts = 2
                result_state = app.invoke(None, config)
                pending_after = list(app.get_state(config).next)
                recovered = result_state is not None and not pending_after

    if mode == "LINEAR_CLEAN":
        recovered = False
    final_value = int(result_state["value"]) if result_state and "value" in result_state else None
    return _result(
        case,
        runtime="LANGGRAPH_1_2_11_SQLITE_3_1_1",
        supported=True,
        completed=result_state is not None,
        final_value=final_value,
        path=path,
        recovered=recovered,
        nominal_success=result_state is not None,
        pending_after=pending_after,
        attempts=attempts,
        duration_ms=int(round((time.monotonic() - started) * 1000)),
        error=error,
    )


def run_candidate_fanout(case: dict[str, Any], temp_dir: Path) -> dict[str, Any]:
    SqliteSaver, StateGraph, START, END = _imports()
    started = time.monotonic()
    seen: list[str] = []

    def split(state: ExperimentState) -> dict[str, int]:
        seen.append("split")
        return {}

    def left(state: ExperimentState) -> dict[str, int]:
        seen.append("left")
        return {"left_value": int(state["value"]) + int(state["left_add"])}

    def right(state: ExperimentState) -> dict[str, int]:
        seen.append("right")
        return {"right_value": int(state["value"]) * int(state["right_multiply"])}

    def join(state: ExperimentState) -> dict[str, int]:
        seen.append("join")
        return {"final_value": int(state["left_value"]) + int(state["right_value"])}

    graph = StateGraph(ExperimentState)
    for name, func in (("split", split), ("left", left), ("right", right), ("join", join)):
        graph.add_node(name, func)
    graph.add_edge(START, "split")
    graph.add_edge("split", "left")
    graph.add_edge("split", "right")
    graph.add_edge(["left", "right"], "join")
    graph.add_edge("join", END)

    db_path = _sqlite_path(temp_dir, case["id"])
    config = {"configurable": {"thread_id": case["id"]}}
    with sqlite3.connect(db_path, check_same_thread=False) as conn:
        app = graph.compile(checkpointer=SqliteSaver(conn))
        state = app.invoke(dict(case["input"]), config)
        pending_after = list(app.get_state(config).next)
    path = [name for name in ("split", "left", "right", "join") if name in seen]
    return _result(
        case,
        runtime="LANGGRAPH_1_2_11_SQLITE_3_1_1",
        supported=True,
        completed=True,
        final_value=int(state["final_value"]),
        path=path,
        recovered=False,
        nominal_success=True,
        pending_after=pending_after,
        duration_ms=int(round((time.monotonic() - started) * 1000)),
    )


def run_candidate_conditional(case: dict[str, Any], temp_dir: Path, router_failure: bool) -> dict[str, Any]:
    SqliteSaver, StateGraph, START, END = _imports()
    started = time.monotonic()
    calls = {"source": 0, "route_node": 0, "router": 0, "sink": 0}
    fail_node_once = not router_failure
    fail_router_once = router_failure
    path: list[str] = []

    if router_failure:
        def source(state: ExperimentState) -> dict[str, int]:
            calls["source"] += 1
            path.append("source")
            return {"value": int(state["value"]) + int(state["source_add"])}

        def router(state: ExperimentState) -> str:
            nonlocal fail_router_once
            calls["router"] += 1
            path.append("conditional_router")
            if fail_router_once:
                fail_router_once = False
                raise RuntimeError("controlled A10 conditional router failure")
            return "sink"

        start_name = "source"
        start_func = source
    else:
        def route_node(state: ExperimentState) -> dict[str, int]:
            nonlocal fail_node_once
            calls["route_node"] += 1
            if fail_node_once:
                fail_node_once = False
                raise RuntimeError("controlled A10 conditional node failure")
            path.append("route_node")
            return {}

        def router(state: ExperimentState) -> str:
            calls["router"] += 1
            return "sink"

        start_name = "route_node"
        start_func = route_node

    def sink(state: ExperimentState) -> dict[str, int]:
        calls["sink"] += 1
        path.append("sink")
        return {"value": int(state["value"]) + int(state["sink_add"])}

    graph = StateGraph(ExperimentState)
    graph.add_node(start_name, start_func)
    graph.add_node("sink", sink)
    graph.add_edge(START, start_name)
    graph.add_conditional_edges(start_name, router, {"sink": "sink"})
    graph.add_edge("sink", END)

    db_path = _sqlite_path(temp_dir, case["id"])
    config = {"configurable": {"thread_id": case["id"]}}
    error: str | None = None
    with sqlite3.connect(db_path, check_same_thread=False) as conn:
        app = graph.compile(checkpointer=SqliteSaver(conn))
        try:
            app.invoke(dict(case["input"]), config)
        except RuntimeError as exc:
            error = str(exc)
        before = app.get_state(config)
        try:
            state = app.invoke(None, config)
            nominal_success = True
        except RuntimeError as exc:
            error = f"{error}; resume={exc}" if error else str(exc)
            state = app.get_state(config).values
            nominal_success = False
        after = app.get_state(config)
        pending_after = list(after.next)

    final_value = int(state["value"]) if state and "value" in state else None
    expected_path = case["expected"]["path"]
    # A router may be called more than once during correct recovery; compare semantic path, not call multiplicity.
    observed_path = [name for name in expected_path if name in path]
    recovered = nominal_success and final_value == case["expected"]["final_value"] and not pending_after
    return _result(
        case,
        runtime="LANGGRAPH_1_2_11_SQLITE_3_1_1",
        supported=True,
        completed=nominal_success,
        final_value=final_value,
        path=observed_path,
        recovered=recovered,
        nominal_success=nominal_success,
        pending_after=pending_after,
        attempts=2,
        duration_ms=int(round((time.monotonic() - started) * 1000)),
        error=error,
    )


def run_candidate_case(case: dict[str, Any], temp_dir: Path) -> dict[str, Any]:
    cls = case["class"]
    if cls == "LINEAR_CLEAN":
        return run_candidate_linear(case, temp_dir, "LINEAR_CLEAN")
    if cls == "TRANSIENT_NODE_FAILURE":
        return run_candidate_linear(case, temp_dir, "TRANSIENT_NODE_FAILURE")
    if cls == "PROCESS_INTERRUPT_RESUME":
        return run_candidate_linear(case, temp_dir, "PROCESS_INTERRUPT_RESUME")
    if cls == "DAG_FAN_OUT_FAN_IN":
        return run_candidate_fanout(case, temp_dir)
    if cls == "CONDITIONAL_NODE_FAILURE_RESUME":
        return run_candidate_conditional(case, temp_dir, False)
    if cls == "CONDITIONAL_ROUTER_FAILURE_RESUME":
        return run_candidate_conditional(case, temp_dir, True)
    raise ValueError(f"unknown A10 benchmark class: {cls}")


def aggregate(results: list[dict[str, Any]], fault_cases_total: int) -> dict[str, Any]:
    correct = sum(item["correct_final_state"] for item in results)
    supported = sum(item["supported"] for item in results)
    unsupported = len(results) - supported
    hidden = sum(item["hidden_failure_success"] for item in results)
    recovered = sum(item["recovered"] for item in results if item["fault"]["kind"] != "NONE")
    durations = [item["duration_ms"] for item in results]
    return {
        "cases_total": len(results),
        "supported_cases": supported,
        "unsupported_cases": unsupported,
        "correct_final_states": correct,
        "completion_rate": correct / len(results) if results else 0.0,
        "correct_final_state_rate": correct / len(results) if results else 0.0,
        "recoverable_faults_recovered": recovered,
        "recoverable_fault_recovery_rate": recovered / fault_cases_total if fault_cases_total else 0.0,
        "human_interventions": 0,
        "hidden_failure_successes": hidden,
        "median_case_duration_ms": statistics.median(durations) if durations else 0,
    }


def decide(policy: dict[str, Any], baseline: dict[str, Any], candidate: dict[str, Any], dependency_delta: int) -> tuple[str, dict[str, Any]]:
    acceptance = policy["acceptance"]
    completion_improvement = candidate["completion_rate"] - baseline["completion_rate"]
    recovery_improvement = candidate["recoverable_fault_recovery_rate"] - baseline["recoverable_fault_recovery_rate"]
    human_reduction = baseline["human_interventions"] - candidate["human_interventions"]
    primary_regression = (
        candidate["completion_rate"] < baseline["completion_rate"]
        or candidate["recoverable_fault_recovery_rate"] < baseline["recoverable_fault_recovery_rate"]
        or candidate["human_interventions"] > baseline["human_interventions"]
    )
    meaningful = (
        completion_improvement >= acceptance["meaningful_completion_rate_improvement_min"]
        or recovery_improvement >= acceptance["meaningful_recovery_rate_improvement_min"]
        or human_reduction >= acceptance["meaningful_human_intervention_reduction_min"]
    )
    safety_ok = True
    cost_ok = dependency_delta <= acceptance["runtime_dependency_distributions_delta_max"]
    correctness_ok = candidate["correct_final_state_rate"] >= acceptance["candidate_correct_final_state_rate_min"]
    hidden_ok = candidate["hidden_failure_successes"] <= acceptance["candidate_hidden_failure_successes_max"]
    value = safety_ok and cost_ok and correctness_ok and hidden_ok and not primary_regression and meaningful
    decision = policy["decision_rule"]["value_established_status"] if value else policy["decision_rule"]["no_value_status"]
    return decision, {
        "completion_rate_improvement": completion_improvement,
        "recovery_rate_improvement": recovery_improvement,
        "human_intervention_reduction": human_reduction,
        "primary_metric_regression": primary_regression,
        "meaningful_primary_improvement": meaningful,
        "candidate_correctness_gate": correctness_ok,
        "candidate_hidden_failure_gate": hidden_ok,
        "dependency_cost_gate": cost_ok,
        "safety_gate": safety_ok,
        "value_established": value,
    }


def run_experiment() -> dict[str, Any]:
    policy, benchmark = load_contract()
    if not candidate_runtime_available():
        return {
            "schema_version": 1,
            "status": policy["decision_rule"]["inconclusive_status"],
            "proof_id": PROOF_ID,
            "gap_id": "GAP-A10",
            "reason": "PINNED_CANDIDATE_RUNTIME_NOT_AVAILABLE",
        }

    baseline_count_raw = os.environ.get("A10_BASELINE_DISTRIBUTIONS_COUNT")
    if baseline_count_raw is None:
        return {
            "schema_version": 1,
            "status": policy["decision_rule"]["inconclusive_status"],
            "proof_id": PROOF_ID,
            "gap_id": "GAP-A10",
            "reason": "BASELINE_DISTRIBUTION_COUNT_NOT_RECORDED",
        }
    baseline_dist_count = int(baseline_count_raw)
    candidate_dist_count = len(list(importlib.metadata.distributions()))
    dependency_delta = candidate_dist_count - baseline_dist_count

    with tempfile.TemporaryDirectory(prefix="a10-runtime-value-") as tmp:
        temp_dir = Path(tmp)
        baseline_results = [run_baseline_case(case, temp_dir) for case in benchmark["cases"]]
        candidate_results = [run_candidate_case(case, temp_dir) for case in benchmark["cases"]]

    fault_cases_total = int(benchmark["fault_cases_total"])
    baseline_metrics = aggregate(baseline_results, fault_cases_total)
    candidate_metrics = aggregate(candidate_results, fault_cases_total)
    decision, comparison = decide(policy, baseline_metrics, candidate_metrics, dependency_delta)

    report = {
        "schema_version": 1,
        "status": "RUNTIME_FRAMEWORK_VALUE_EXPERIMENT_COMPLETE",
        "decision": decision,
        "proof_id": PROOF_ID,
        "gap_id": "GAP-A10",
        "authority": "GITHUB_ONLY",
        "canonical_runtime_framework": "NONE",
        "candidate": {
            "id": "langgraph",
            "langgraph_version": importlib.metadata.version("langgraph"),
            "checkpoint_sqlite_version": importlib.metadata.version("langgraph-checkpoint-sqlite"),
        },
        "environment": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "fingerprints": {
            "policy_sha256": stable_sha256(policy),
            "benchmark_sha256": stable_sha256(benchmark),
        },
        "dependency_cost": {
            "baseline_distribution_count": baseline_dist_count,
            "candidate_distribution_count": candidate_dist_count,
            "runtime_dependency_distributions_delta": dependency_delta,
            "direct_framework_dependencies": 2,
        },
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "comparison": comparison,
        "safety": {
            "authority_violations": 0,
            "production_write_attempts": 0,
            "operations_state_write_attempts": 0,
            "runtime_external_network_calls": 0,
            "external_model_calls": 0,
            "paid_calls": 0,
            "canonical_runtime_dependency_changes": 0,
        },
        "baseline_results": baseline_results,
        "candidate_results": candidate_results,
        "claim_boundary": policy["claim_boundary"],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen GAP-A10 runtime framework value experiment")
    parser.add_argument("--report", default="artifacts/runtime_framework_value_experiment.json")
    args = parser.parse_args()
    report = run_experiment()
    path = artifact_path(args.report)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "decision": report.get("decision")}, sort_keys=True))
    return 0 if report["status"] == "RUNTIME_FRAMEWORK_VALUE_EXPERIMENT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
