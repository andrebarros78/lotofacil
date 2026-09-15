from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "governance" / "agents" / "agents.json"
SKILLS_PATH = ROOT / "governance" / "agents" / "skills.json"
ACQUISITIONS_PATH = ROOT / "governance" / "agents" / "acquisitions.json"
HANDOFF_SCHEMA_PATH = ROOT / "governance" / "agents" / "handoff.schema.json"
REDTEAM_PATH = ROOT / "governance" / "agents" / "redteam_cases.json"
CAPABILITY_MISSIONS_PATH = ROOT / "governance" / "agents" / "capability_missions.json"
TOOL_BINDINGS_PATH = ROOT / "governance" / "agents" / "tool_bindings.json"
AGENTS_MD_PATH = ROOT / "AGENTS.md"

REQUIRED_HANDOFF_FIELDS = {
    "agent_id",
    "task_id",
    "evidence_refs",
    "findings",
    "proposed_actions",
    "risk_level",
    "requires_approval",
    "scientific_claim_level",
}

MANDATORY_AGENT_PROHIBITIONS = {
    "direct_main_write",
    "direct_operations_state_write",
}

VALID_ACQUISITION_DECISIONS = {
    "ACQUIRED_AS_REFERENCE_AND_ADAPTER_TARGET",
    "ACQUIRED_AS_INTEROPERABILITY_STANDARD",
    "ACQUIRED_AS_GOVERNANCE_REFERENCE",
    "EVALUATED_NOT_ACQUIRED",
    "ON_DEMAND_ONLY",
    "DISCOVERY_ONLY_UNTRUSTED",
}

VALID_REDTEAM_DECISIONS = {"REJECT", "REQUIRE_APPROVAL"}
VALID_TOOL_KINDS = {"script", "pytest"}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate() -> dict:
    require(AGENTS_MD_PATH.is_file(), "AGENTS.md missing")
    for path in (
        AGENTS_PATH,
        SKILLS_PATH,
        ACQUISITIONS_PATH,
        HANDOFF_SCHEMA_PATH,
        REDTEAM_PATH,
        CAPABILITY_MISSIONS_PATH,
        TOOL_BINDINGS_PATH,
    ):
        require(path.is_file(), f"missing registry: {path.relative_to(ROOT)}")

    agents_doc = load_json(AGENTS_PATH)
    skills_doc = load_json(SKILLS_PATH)
    acquisitions_doc = load_json(ACQUISITIONS_PATH)
    handoff_schema = load_json(HANDOFF_SCHEMA_PATH)
    redteam_doc = load_json(REDTEAM_PATH)
    capability_doc = load_json(CAPABILITY_MISSIONS_PATH)
    tools_doc = load_json(TOOL_BINDINGS_PATH)

    require(agents_doc.get("schema_version") == 1, "unsupported agents schema")
    require(skills_doc.get("schema_version") == 1, "unsupported skills schema")
    require(acquisitions_doc.get("schema_version") == 1, "unsupported acquisitions schema")
    require(redteam_doc.get("schema_version") == 1, "unsupported red-team schema")
    require(capability_doc.get("schema_version") == 1, "unsupported capability schema")
    require(tools_doc.get("schema_version") == 1, "unsupported tool binding schema")
    require(agents_doc.get("authority") == "GITHUB_ONLY", "agent authority must be GITHUB_ONLY")
    require(agents_doc.get("canonical_code_branch") == "main", "canonical code branch drift")
    require(agents_doc.get("canonical_state_branch") == "operations/state", "canonical state branch drift")

    handoff_fields = set(agents_doc.get("handoff_required_fields", []))
    require(REQUIRED_HANDOFF_FIELDS <= handoff_fields, "agent handoff contract incomplete")
    require(handoff_schema.get("type") == "object", "handoff schema must describe an object")
    require(handoff_schema.get("additionalProperties") is False, "handoff schema must reject undeclared fields")
    require(set(handoff_schema.get("required", [])) == handoff_fields, "handoff schema/registry drift")
    require(handoff_fields <= set(handoff_schema.get("properties", {})), "handoff schema properties incomplete")

    skills = skills_doc.get("skills", [])
    skill_ids = [skill.get("id") for skill in skills]
    require(len(skill_ids) >= 20, "skill registry unexpectedly small")
    require(None not in skill_ids, "skill without id")
    require(len(skill_ids) == len(set(skill_ids)), "duplicate skill id")
    known_skills = set(skill_ids)

    for skill in skills:
        require(bool(skill.get("description")), f"skill {skill['id']} missing description")
        require(bool(skill.get("source")), f"skill {skill['id']} missing source")
        require(bool(skill.get("source_url")), f"skill {skill['id']} missing source_url")

    agents = agents_doc.get("agents", [])
    agent_ids = [agent.get("id") for agent in agents]
    require(len(agent_ids) >= 8, "agent registry unexpectedly small")
    require(None not in agent_ids, "agent without id")
    require(len(agent_ids) == len(set(agent_ids)), "duplicate agent id")
    known_agents = set(agent_ids)

    all_prohibited_actions: set[str] = set()
    for agent in agents:
        agent_id = agent["id"]
        agent_skills = set(agent.get("skills", []))
        prohibited = set(agent.get("prohibited_actions", []))
        all_prohibited_actions.update(prohibited)
        require(agent_skills, f"agent {agent_id} has no skills")
        require(agent_skills <= known_skills, f"agent {agent_id} references unknown skills")
        require(MANDATORY_AGENT_PROHIBITIONS <= prohibited, f"agent {agent_id} can mutate canonical branches directly")
        require(bool(agent.get("allowed_actions")), f"agent {agent_id} has no allowed actions")
        require(bool(agent.get("role")), f"agent {agent_id} missing role")

    by_id = {agent["id"]: agent for agent in agents}
    for scientific_agent in ("scientific-methodologist", "statistical-validator"):
        require(scientific_agent in by_id, f"missing critical agent {scientific_agent}")
        require(
            "lockbox_retuning" in by_id[scientific_agent]["prohibited_actions"],
            f"{scientific_agent} must forbid lockbox retuning",
        )

    require("security-tool-gate" in by_id, "missing security-tool-gate")
    require("agent-evaluator-redteam" in by_id, "missing agent-evaluator-redteam")
    require("acquisition-scout" in by_id, "missing acquisition-scout")

    policy = acquisitions_doc.get("policy", {})
    require(policy.get("runtime_dependency_requires_separate_experiment") is True, "runtime dependency experiment gate disabled")
    require(policy.get("paid_service_requires_explicit_approval") is True, "paid service approval gate disabled")
    require(policy.get("community_code_is_untrusted_until_reviewed") is True, "community trust boundary disabled")
    require(policy.get("vendoring_without_license_review_forbidden") is True, "license gate disabled")
    require(policy.get("production_core_must_remain_framework_independent_by_default") is True, "framework independence disabled")

    acquisitions = acquisitions_doc.get("acquisitions", [])
    acquisition_ids = [item.get("id") for item in acquisitions]
    require(len(acquisition_ids) >= 8, "acquisition registry unexpectedly small")
    require(len(acquisition_ids) == len(set(acquisition_ids)), "duplicate acquisition id")

    acquired_count = 0
    for item in acquisitions:
        item_id = item.get("id")
        require(item.get("decision") in VALID_ACQUISITION_DECISIONS, f"invalid acquisition decision for {item_id}")
        require(bool(item.get("source_url")), f"acquisition {item_id} missing source_url")
        require(bool(item.get("reason")), f"acquisition {item_id} missing reason")
        require(bool(item.get("next_gate")), f"acquisition {item_id} missing next_gate")
        require(item.get("runtime_dependency") is False, f"acquisition {item_id} unexpectedly became a runtime dependency")
        if str(item.get("decision", "")).startswith("ACQUIRED_AS_"):
            acquired_count += 1

    require(acquired_count >= 3, "expected at least three controlled reference acquisitions")

    redteam_cases = redteam_doc.get("cases", [])
    redteam_ids = [case.get("id") for case in redteam_cases]
    require(len(redteam_ids) >= 8, "red-team corpus unexpectedly small")
    require(len(redteam_ids) == len(set(redteam_ids)), "duplicate red-team case id")
    for case in redteam_cases:
        case_id = case.get("id")
        require(bool(case.get("scenario")), f"red-team case {case_id} missing scenario")
        require(case.get("expected_decision") in VALID_REDTEAM_DECISIONS, f"invalid red-team decision for {case_id}")
        require(case.get("expected_guardrail") in all_prohibited_actions, f"red-team guardrail not enforced by any agent: {case_id}")

    require(capability_doc.get("authority") == "GITHUB_ONLY", "capability authority drift")
    require(capability_doc.get("runtime_framework") == "NONE", "capability baseline unexpectedly uses agent runtime")
    mission_policy = capability_doc.get("mission_policy", {})
    require(mission_policy.get("read_only_only") is True, "capability read-only policy disabled")
    require(mission_policy.get("shell_execution_forbidden") is True, "capability shell prohibition disabled")
    require(mission_policy.get("direct_main_write_forbidden") is True, "capability main-write prohibition disabled")
    require(mission_policy.get("direct_operations_state_write_forbidden") is True, "capability state-write prohibition disabled")

    tool_policy = tools_doc.get("policy", {})
    require(tool_policy.get("python_executable_only") is True, "tool python-only policy disabled")
    require(tool_policy.get("shell_false_required") is True, "tool shell=False policy disabled")
    require(tool_policy.get("write_effects_forbidden") is True, "tool write-effect prohibition disabled")
    require(tool_policy.get("network_required") is False, "baseline tools unexpectedly require network")

    tools = tools_doc.get("tools", [])
    tool_ids = [tool.get("id") for tool in tools]
    require(len(tool_ids) >= 8, "capability tool registry unexpectedly small")
    require(None not in tool_ids, "tool without id")
    require(len(tool_ids) == len(set(tool_ids)), "duplicate capability tool id")
    known_tools = set(tool_ids)
    for tool in tools:
        require(tool.get("kind") in VALID_TOOL_KINDS, f"unsupported capability tool kind: {tool.get('id')}")

    missions = capability_doc.get("missions", [])
    mission_ids = [mission.get("id") for mission in missions]
    require(len(mission_ids) >= 8, "capability mission registry unexpectedly small")
    require(None not in mission_ids, "capability mission without id")
    require(len(mission_ids) == len(set(mission_ids)), "duplicate capability mission id")
    for mission in missions:
        mission_id = mission.get("id")
        require(mission.get("agent_id") in known_agents, f"unknown mission agent: {mission_id}")
        require(mission.get("tool_id") in known_tools, f"unknown mission tool: {mission_id}")
        require(mission.get("risk_level") == "LOW", f"non-low-risk mission in autonomous baseline: {mission_id}")
        require(mission.get("acceptance") == "exit_code_zero", f"unsupported mission acceptance: {mission_id}")

    return {
        "status": "AGENT_ECOSYSTEM_PASS",
        "agents": len(agents),
        "skills": len(skills),
        "acquisitions": len(acquisitions),
        "controlled_reference_acquisitions": acquired_count,
        "redteam_cases": len(redteam_cases),
        "capability_missions": len(missions),
        "capability_tools": len(tools),
        "runtime_framework_dependencies": 0,
        "authority": agents_doc["authority"],
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
