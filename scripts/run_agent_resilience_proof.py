from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_agent_capability_proof import (  # noqa: E402
    _stable_json_sha256,
    build_command,
    load_contract,
    validate_contract,
)

POLICY_PATH = ROOT / "governance" / "agents" / "resilience_policy.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_hash(payload: Any) -> str:
    return _stable_json_sha256(payload)


def artifact_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    artifacts = (ROOT / "artifacts").resolve()
    if path != artifacts and artifacts not in path.parents:
        raise ValueError("resilience proof paths must remain under artifacts/")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def definition_fingerprint() -> str:
    missions_doc, tools_doc, agents_doc, skills_doc = load_contract()
    return stable_hash(
        {
            "agents": agents_doc["agents"],
            "skills": skills_doc["skills"],
            "missions": missions_doc["missions"],
            "tools": tools_doc["tools"],
        }
    )


def clean_replay_fingerprint() -> str:
    missions_doc, _, _, _ = load_contract()
    material = [
        {
            "mission_id": mission["id"],
            "agent_id": mission["agent_id"],
            "required_skills": mission["required_skills"],
            "tool_id": mission["tool_id"],
            "returncode": 0,
            "status": "PASS",
        }
        for mission in missions_doc["missions"]
    ]
    return stable_hash(material)


CLEAN_REPLAY_FINGERPRINT = clean_replay_fingerprint()


def checkpoint_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key != "checkpoint_payload_sha256"
    }
    return stable_hash(canonical)


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["checkpoint_payload_sha256"] = checkpoint_hash(payload)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temp.replace(path)


def load_checkpoint(
    path: Path, expected_definition_fingerprint: str
) -> dict[str, Any]:
    payload = load_json(path)
    recorded_hash = payload.get("checkpoint_payload_sha256")
    if not recorded_hash or recorded_hash != checkpoint_hash(payload):
        raise ValueError("checkpoint payload hash mismatch")
    if payload.get("definition_fingerprint_sha256") != expected_definition_fingerprint:
        raise ValueError("checkpoint definition fingerprint drift")
    results = payload.get("results", [])
    if any(result.get("status") != "PASS" for result in results):
        raise ValueError("checkpoint contains non-passing completed mission")
    next_index = payload.get("next_index")
    if not isinstance(next_index, int) or next_index != len(results):
        raise ValueError("checkpoint next_index/result count mismatch")
    return payload


def execute_tool(
    command: list[str], timeout: int
) -> tuple[int, str, str, bool, int]:
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=os.environ.copy(),
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    duration_ms = int(round((time.monotonic() - started) * 1000))
    return returncode, stdout, stderr, timed_out, duration_ms


def mission_result(
    *,
    ordinal: int,
    mission: dict[str, Any],
    command: list[str],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    final = attempts[-1]
    status = (
        "PASS" if final["returncode"] == 0 and not final["timed_out"] else "FAIL"
    )
    return {
        "ordinal": ordinal,
        "mission_id": mission["id"],
        "agent_id": mission["agent_id"],
        "required_skills": mission["required_skills"],
        "tool_id": mission["tool_id"],
        "status": status,
        "returncode": final["returncode"],
        "timed_out": final["timed_out"],
        "duration_ms": sum(attempt["duration_ms"] for attempt in attempts),
        "attempts": attempts,
        "command": command,
        "evidence_ref": f"resilience-proof:{mission['id']}:{ordinal}",
    }


def build_handoff(
    mission: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    return {
        "agent_id": mission["agent_id"],
        "task_id": mission["id"],
        "evidence_refs": [result["evidence_ref"]],
        "findings": [
            f"{mission['id']} {result['status']} after {len(result['attempts'])} attempt(s)"
        ],
        "proposed_actions": []
        if result["status"] == "PASS"
        else ["block_promotion_and_investigate_failure"],
        "risk_level": mission["risk_level"],
        "requires_approval": False,
        "scientific_claim_level": mission["scientific_claim_level"],
    }


def run(
    *,
    checkpoint: Path,
    report_path: Path,
    resume: bool,
    interrupt_after: int | None,
    inject_transient_failure: str | None,
) -> tuple[dict[str, Any], int]:
    contract = validate_contract()
    policy = load_json(POLICY_PATH)
    missions_doc, tools_doc, _, _ = load_contract()
    tools_by_id = {tool["id"]: tool for tool in tools_doc["tools"]}
    missions = missions_doc["missions"]
    timeout = int(tools_doc["policy"].get("timeout_seconds", 180))
    max_retries = int(policy["retry"]["max_retries_per_mission"])
    interrupt_code = int(policy["fault_injection"]["process_interruption_exit_code"])
    definition_sha = definition_fingerprint()
    clean_replay_sha = clean_replay_fingerprint()

    results: list[dict[str, Any]] = []
    checkpoint_resumes = 0
    injected_interruptions = 0
    transient_failures_injected = 0
    transient_failures_recovered = 0

    start_index = 0
    if resume:
        state = load_checkpoint(checkpoint, definition_sha)
        results = list(state["results"])
        start_index = int(state["next_index"])
        checkpoint_resumes = int(state.get("checkpoint_resumes", 0)) + 1
        injected_interruptions = int(state.get("injected_interruptions", 0))
        transient_failures_injected = int(
            state.get("transient_failures_injected", 0)
        )
        transient_failures_recovered = int(
            state.get("transient_failures_recovered", 0)
        )

    started = time.monotonic()
    for index in range(start_index, len(missions)):
        mission = missions[index]
        command = build_command(tools_by_id[mission["tool_id"]])
        attempts: list[dict[str, Any]] = []

        if inject_transient_failure == mission["id"]:
            transient_failures_injected += 1
            attempts.append(
                {
                    "attempt": 1,
                    "kind": "CONTROLLED_TRANSIENT_FAILURE",
                    "returncode": 70,
                    "timed_out": False,
                    "duration_ms": 0,
                    "stdout_sha256": hashlib.sha256(b"").hexdigest(),
                    "stderr_sha256": hashlib.sha256(
                        b"controlled transient failure"
                    ).hexdigest(),
                }
            )

        next_attempt_number = len(attempts) + 1
        retries_available = max_retries if attempts else 0
        while True:
            returncode, stdout, stderr, timed_out, duration_ms = execute_tool(
                command, timeout
            )
            attempts.append(
                {
                    "attempt": next_attempt_number,
                    "kind": "TOOL_EXECUTION",
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "duration_ms": duration_ms,
                    "stdout_sha256": hashlib.sha256(
                        stdout.encode("utf-8")
                    ).hexdigest(),
                    "stderr_sha256": hashlib.sha256(
                        stderr.encode("utf-8")
                    ).hexdigest(),
                }
            )
            if returncode == 0 and not timed_out:
                if (
                    len(attempts) > 1
                    and attempts[0]["kind"] == "CONTROLLED_TRANSIENT_FAILURE"
                ):
                    transient_failures_recovered += 1
                break
            if retries_available <= 0:
                break
            retries_available -= 1
            next_attempt_number += 1

        result = mission_result(
            ordinal=index + 1,
            mission=mission,
            command=command,
            attempts=attempts,
        )
        results.append(result)

        state = {
            "schema_version": 1,
            "baseline_type": policy["baseline_type"],
            "definition_fingerprint_sha256": definition_sha,
            "next_index": index + 1,
            "results": results,
            "checkpoint_resumes": checkpoint_resumes,
            "injected_interruptions": injected_interruptions,
            "transient_failures_injected": transient_failures_injected,
            "transient_failures_recovered": transient_failures_recovered,
        }
        write_checkpoint(checkpoint, state)

        if result["status"] != "PASS":
            break

        if interrupt_after is not None and (index + 1) == interrupt_after:
            injected_interruptions += 1
            state["injected_interruptions"] = injected_interruptions
            write_checkpoint(checkpoint, state)
            interrupted_report = {
                "schema_version": 1,
                "status": "AGENT_RESILIENCE_EXPECTED_INTERRUPTION",
                "baseline_type": policy["baseline_type"],
                "definition_fingerprint_sha256": definition_sha,
                "completed_before_interruption": len(results),
                "next_index": index + 1,
                "checkpoint_payload_sha256": load_json(checkpoint)[
                    "checkpoint_payload_sha256"
                ],
                "expected_exit_code": interrupt_code,
            }
            report_path.write_text(
                json.dumps(interrupted_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return interrupted_report, interrupt_code

    passed = sum(result["status"] == "PASS" for result in results)
    failed = len(results) - passed
    stable_replay_material = [
        {
            "mission_id": result["mission_id"],
            "agent_id": result["agent_id"],
            "required_skills": result["required_skills"],
            "tool_id": result["tool_id"],
            "returncode": result["returncode"],
            "status": result["status"],
        }
        for result in results
    ]
    replay_sha = stable_hash(stable_replay_material)
    handoffs = [
        build_handoff(missions[result["ordinal"] - 1], result) for result in results
    ]
    success = (
        len(results) == len(missions)
        and failed == 0
        and checkpoint_resumes
        >= int(policy["success_criteria"]["checkpoint_resume_count_min"])
        and transient_failures_recovered
        >= int(
            policy["success_criteria"]["transient_failure_recovered_count_min"]
        )
        and replay_sha == clean_replay_sha
    )
    report = {
        "schema_version": 1,
        "status": "AGENT_RESILIENCE_PROOF_PASS"
        if success
        else "AGENT_RESILIENCE_PROOF_FAIL",
        "authority": contract["authority"],
        "runtime_framework": contract["runtime_framework"],
        "baseline_type": policy["baseline_type"],
        "environment": {
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "metrics": {
            "missions_total": len(missions),
            "missions_completed": len(results),
            "missions_passed": passed,
            "missions_failed": failed,
            "agents_bound": contract["bound_agents"],
            "skills_assigned": contract["assigned_skills"],
            "checkpoint_resumes": checkpoint_resumes,
            "injected_interruptions": injected_interruptions,
            "transient_failures_injected": transient_failures_injected,
            "transient_failures_recovered": transient_failures_recovered,
            "human_interventions": 0,
            "tool_binding_violations": 0,
            "skill_binding_violations": 0,
            "runtime_framework_dependencies": 0,
            "total_duration_ms_this_process": int(
                round((time.monotonic() - started) * 1000)
            ),
        },
        "definition_fingerprint_sha256": definition_sha,
        "replay_fingerprint_sha256": replay_sha,
        "clean_baseline_replay_fingerprint_sha256": clean_replay_sha,
        "checkpoint_payload_sha256": load_json(checkpoint)[
            "checkpoint_payload_sha256"
        ],
        "results": results,
        "handoffs": handoffs,
        "limitations": [
            "Faults are controlled synthetic benchmark faults, not evidence of recovery from every real failure class.",
            "Resume is deterministic from a verified artifact checkpoint and does not prove dynamic replanning.",
            "This proof does not require or establish value for an external agent runtime framework.",
            "This proof cannot alter predictive_evidence or reopen the scientific lockbox.",
        ],
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report, 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded SARE agent resilience proof."
    )
    parser.add_argument(
        "--checkpoint", default="artifacts/agent_resilience_checkpoint.json"
    )
    parser.add_argument(
        "--report", default="artifacts/agent_resilience_proof.json"
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--interrupt-after", type=int)
    parser.add_argument("--inject-transient-failure")
    args = parser.parse_args()

    checkpoint = artifact_path(args.checkpoint)
    report_path = artifact_path(args.report)
    report, exit_code = run(
        checkpoint=checkpoint,
        report_path=report_path,
        resume=args.resume,
        interrupt_after=args.interrupt_after,
        inject_transient_failure=args.inject_transient_failure,
    )
    print(
        json.dumps(
            {"status": report["status"], "metrics": report.get("metrics")},
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
