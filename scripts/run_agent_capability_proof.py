from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MISSIONS_PATH = ROOT / "governance" / "agents" / "capability_missions.json"
TOOLS_PATH = ROOT / "governance" / "agents" / "tool_bindings.json"
AGENTS_PATH = ROOT / "governance" / "agents" / "agents.json"
SKILLS_PATH = ROOT / "governance" / "agents" / "skills.json"

SAFE_SCRIPT_TARGETS = {
    "scripts/validate_agent_ecosystem.py",
}
ALLOWED_CLAIM_LEVELS = {
    "NONE",
    "DESCRIPTIVE",
    "RETROSPECTIVE",
    "SYNTHETIC_VALIDATION",
    "CONFIRMATORY_NOT_ESTABLISHED",
    "REPLICATED",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(encoded)


def _safe_repo_path(relative: str, required_prefix: str) -> Path:
    if not relative.startswith(required_prefix):
        raise ValueError(f"target outside allowed prefix: {relative}")
    candidate = (ROOT / relative).resolve()
    root = ROOT.resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"target escapes repository: {relative}")
    if not candidate.is_file():
        raise ValueError(f"target does not exist: {relative}")
    return candidate


def load_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    missions_doc = _load_json(MISSIONS_PATH)
    tools_doc = _load_json(TOOLS_PATH)
    agents_doc = _load_json(AGENTS_PATH)
    skills_doc = _load_json(SKILLS_PATH)
    for label, doc in (
        ("capability mission", missions_doc),
        ("tool binding", tools_doc),
        ("agent", agents_doc),
        ("skill", skills_doc),
    ):
        if doc.get("schema_version") != 1:
            raise ValueError(f"unsupported {label} schema")
    if missions_doc.get("authority") != "GITHUB_ONLY":
        raise ValueError("capability proof authority drift")
    if agents_doc.get("authority") != "GITHUB_ONLY":
        raise ValueError("agent authority drift")
    if missions_doc.get("runtime_framework") != "NONE":
        raise ValueError("baseline must remain framework-independent")
    return missions_doc, tools_doc, agents_doc, skills_doc


def validate_contract() -> dict[str, Any]:
    missions_doc, tools_doc, agents_doc, skills_doc = load_contract()
    agents = agents_doc.get("agents", [])
    skills = skills_doc.get("skills", [])
    tools = tools_doc.get("tools", [])
    missions = missions_doc.get("missions", [])

    agent_ids = [agent.get("id") for agent in agents]
    skill_ids = [skill.get("id") for skill in skills]
    tool_ids = [tool.get("id") for tool in tools]
    mission_ids = [mission.get("id") for mission in missions]

    for label, ids in (
        ("agent", agent_ids),
        ("skill", skill_ids),
        ("tool", tool_ids),
        ("mission", mission_ids),
    ):
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate {label} id")

    if len(missions) < 12:
        raise ValueError("capability baseline unexpectedly small")

    agents_by_id = {agent["id"]: agent for agent in agents}
    skills_by_id = {skill["id"]: skill for skill in skills}
    tools_by_id = {tool["id"]: tool for tool in tools}
    bound_agents: set[str] = set()
    assigned_skills: set[str] = set()

    for agent in agents:
        declared_skills = agent.get("skills")
        if not isinstance(declared_skills, list) or not declared_skills:
            raise ValueError(f"agent without skills: {agent.get('id')}")
        unknown = sorted(set(declared_skills) - set(skills_by_id))
        if unknown:
            raise ValueError(f"agent {agent['id']} has unknown skills: {unknown}")
        assigned_skills.update(declared_skills)

    unassigned_skills = sorted(set(skills_by_id) - assigned_skills)
    if unassigned_skills:
        raise ValueError(f"catalog skills without agent assignment: {unassigned_skills}")

    for tool in tools:
        kind = tool.get("kind")
        if kind == "script":
            target = tool.get("target")
            if target not in SAFE_SCRIPT_TARGETS:
                raise ValueError(f"unsafe script binding: {target}")
            _safe_repo_path(target, "scripts/")
        elif kind == "pytest":
            targets = tool.get("targets")
            if not isinstance(targets, list) or not targets:
                raise ValueError(f"pytest binding without targets: {tool.get('id')}")
            for target in targets:
                if not target.startswith("tests/test_") or not target.endswith(".py"):
                    raise ValueError(f"unsafe pytest target: {target}")
                _safe_repo_path(target, "tests/")
        else:
            raise ValueError(f"unsupported tool kind: {kind}")

    for mission in missions:
        agent_id = mission.get("agent_id")
        tool_id = mission.get("tool_id")
        required_skills = mission.get("required_skills")
        if agent_id not in agents_by_id:
            raise ValueError(f"unknown mission agent: {agent_id}")
        if tool_id not in tools_by_id:
            raise ValueError(f"unknown mission tool: {tool_id}")
        if not isinstance(required_skills, list) or not required_skills:
            raise ValueError(f"mission without required_skills: {mission.get('id')}")
        unknown_required = sorted(set(required_skills) - set(skills_by_id))
        if unknown_required:
            raise ValueError(
                f"mission {mission['id']} has unknown required skills: {unknown_required}"
            )
        missing = sorted(set(required_skills) - set(agents_by_id[agent_id]["skills"]))
        if missing:
            raise ValueError(
                f"mission {mission['id']} agent {agent_id} lacks required skills: {missing}"
            )
        if mission.get("risk_level") != "LOW":
            raise ValueError(f"baseline mission is not LOW risk: {mission.get('id')}")
        if mission.get("scientific_claim_level") not in ALLOWED_CLAIM_LEVELS:
            raise ValueError(f"invalid claim level: {mission.get('id')}")
        if mission.get("acceptance") != "exit_code_zero":
            raise ValueError(f"unsupported acceptance rule: {mission.get('id')}")
        bound_agents.add(agent_id)

    unbound_agents = sorted(set(agents_by_id) - bound_agents)
    if unbound_agents:
        raise ValueError(f"agents without executable mission binding: {unbound_agents}")

    policy = missions_doc.get("mission_policy", {})
    if policy.get("read_only_only") is not True:
        raise ValueError("read-only baseline disabled")
    if policy.get("shell_execution_forbidden") is not True:
        raise ValueError("shell prohibition disabled")
    if policy.get("direct_main_write_forbidden") is not True:
        raise ValueError("main write prohibition disabled")
    if policy.get("direct_operations_state_write_forbidden") is not True:
        raise ValueError("operations/state write prohibition disabled")

    tool_policy = tools_doc.get("policy", {})
    if tool_policy.get("shell_false_required") is not True:
        raise ValueError("tool shell=False policy disabled")
    if tool_policy.get("write_effects_forbidden") is not True:
        raise ValueError("tool write-effect prohibition disabled")

    return {
        "missions": len(missions),
        "tools": len(tools),
        "agents": len(agents),
        "skills": len(skills),
        "bound_agents": len(bound_agents),
        "assigned_skills": len(assigned_skills),
        "all_agents_bound": len(bound_agents) == len(agents),
        "all_skills_assigned": len(assigned_skills) == len(skills),
        "runtime_framework": missions_doc["runtime_framework"],
        "authority": missions_doc["authority"],
    }


def build_command(tool: dict[str, Any]) -> list[str]:
    kind = tool["kind"]
    if kind == "script":
        return [sys.executable, tool["target"]]
    if kind == "pytest":
        return [sys.executable, "-m", "pytest", "-q", *tool["targets"]]
    raise ValueError(f"unsupported tool kind: {kind}")


def build_plan() -> list[dict[str, Any]]:
    missions_doc, tools_doc, agents_doc, _ = load_contract()
    validate_contract()
    tools_by_id = {tool["id"]: tool for tool in tools_doc["tools"]}
    agents_by_id = {agent["id"]: agent for agent in agents_doc["agents"]}
    plan: list[dict[str, Any]] = []
    for mission in missions_doc["missions"]:
        tool = tools_by_id[mission["tool_id"]]
        agent = agents_by_id[mission["agent_id"]]
        plan.append(
            {
                "mission_id": mission["id"],
                "agent_id": mission["agent_id"],
                "required_skills": mission["required_skills"],
                "agent_skills": agent["skills"],
                "tool_id": mission["tool_id"],
                "purpose": mission["purpose"],
                "risk_level": mission["risk_level"],
                "scientific_claim_level": mission["scientific_claim_level"],
                "command": build_command(tool),
            }
        )
    return plan


def execute(output_path: Path) -> dict[str, Any]:
    contract = validate_contract()
    missions_doc, tools_doc, agents_doc, skills_doc = load_contract()
    tools_by_id = {tool["id"]: tool for tool in tools_doc["tools"]}
    timeout = int(tools_doc.get("policy", {}).get("timeout_seconds", 180))

    results: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    started = time.monotonic()

    for ordinal, mission in enumerate(missions_doc["missions"], start=1):
        tool = tools_by_id[mission["tool_id"]]
        command = build_command(tool)
        task_started = time.monotonic()
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

        duration_ms = int(round((time.monotonic() - task_started) * 1000))
        status = "PASS" if returncode == 0 and not timed_out else "FAIL"
        evidence_ref = f"capability-proof:{mission['id']}:{ordinal}"
        result = {
            "ordinal": ordinal,
            "mission_id": mission["id"],
            "agent_id": mission["agent_id"],
            "required_skills": mission["required_skills"],
            "tool_id": mission["tool_id"],
            "status": status,
            "returncode": returncode,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout_sha256": _sha256_text(stdout),
            "stderr_sha256": _sha256_text(stderr),
            "command": command,
            "evidence_ref": evidence_ref,
        }
        results.append(result)
        handoffs.append(
            {
                "agent_id": mission["agent_id"],
                "task_id": mission["id"],
                "evidence_refs": [evidence_ref],
                "findings": [f"{mission['id']} {status} with returncode={returncode}"],
                "proposed_actions": [] if status == "PASS" else ["block_promotion_and_investigate_failure"],
                "risk_level": mission["risk_level"],
                "requires_approval": False,
                "scientific_claim_level": mission["scientific_claim_level"],
            }
        )

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
    definition_material = {
        "agents": agents_doc["agents"],
        "skills": skills_doc["skills"],
        "missions": missions_doc["missions"],
        "tools": tools_doc["tools"],
    }
    total_duration_ms = int(round((time.monotonic() - started) * 1000))
    status = "AGENT_CAPABILITY_PROOF_PASS" if failed == 0 else "AGENT_CAPABILITY_PROOF_FAIL"

    report = {
        "schema_version": 1,
        "status": status,
        "authority": contract["authority"],
        "runtime_framework": contract["runtime_framework"],
        "baseline_type": "BOUNDED_DETERMINISTIC_AUTONOMY_WITH_SKILL_BINDING",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        },
        "metrics": {
            "missions_total": len(results),
            "missions_passed": passed,
            "missions_failed": failed,
            "agents_bound": contract["bound_agents"],
            "skills_assigned": contract["assigned_skills"],
            "autonomous_completion_rate": passed / len(results) if results else 0.0,
            "human_interventions": 0,
            "tool_binding_violations": 0,
            "skill_binding_violations": 0,
            "runtime_framework_dependencies": 0,
            "total_duration_ms": total_duration_ms,
        },
        "definition_fingerprint_sha256": _stable_json_sha256(definition_material),
        "replay_fingerprint_sha256": _stable_json_sha256(stable_replay_material),
        "results": results,
        "handoffs": handoffs,
        "limitations": [
            "This proves bounded deterministic autonomous execution of predeclared read-only missions with explicit agent-to-skill-to-tool bindings; it does not prove open-ended LLM planning.",
            "No paid model, new account or external agent runtime framework is exercised by this baseline.",
            "Passing capability missions does not change predictive_evidence and cannot promote a scientific claim.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded SARE agent capability proof.")
    parser.add_argument("--output", default="agent-capability-proof.json")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.plan:
        payload = {
            "status": "AGENT_CAPABILITY_PLAN_VALID",
            "contract": validate_contract(),
            "plan": build_plan(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    report = execute((ROOT / args.output).resolve())
    print(
        json.dumps(
            {
                "status": report["status"],
                "metrics": report["metrics"],
                "replay_fingerprint_sha256": report["replay_fingerprint_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "AGENT_CAPABILITY_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
