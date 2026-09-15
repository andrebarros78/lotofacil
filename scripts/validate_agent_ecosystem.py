from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "governance" / "agents" / "agents.json"
SKILLS_PATH = ROOT / "governance" / "agents" / "skills.json"
ACQUISITIONS_PATH = ROOT / "governance" / "agents" / "acquisitions.json"
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


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate() -> dict:
    require(AGENTS_MD_PATH.is_file(), "AGENTS.md missing")
    for path in (AGENTS_PATH, SKILLS_PATH, ACQUISITIONS_PATH):
        require(path.is_file(), f"missing registry: {path.relative_to(ROOT)}")

    agents_doc = load_json(AGENTS_PATH)
    skills_doc = load_json(SKILLS_PATH)
    acquisitions_doc = load_json(ACQUISITIONS_PATH)

    require(agents_doc.get("schema_version") == 1, "unsupported agents schema")
    require(skills_doc.get("schema_version") == 1, "unsupported skills schema")
    require(acquisitions_doc.get("schema_version") == 1, "unsupported acquisitions schema")
    require(agents_doc.get("authority") == "GITHUB_ONLY", "agent authority must be GITHUB_ONLY")
    require(agents_doc.get("canonical_code_branch") == "main", "canonical code branch drift")
    require(agents_doc.get("canonical_state_branch") == "operations/state", "canonical state branch drift")

    handoff_fields = set(agents_doc.get("handoff_required_fields", []))
    require(REQUIRED_HANDOFF_FIELDS <= handoff_fields, "agent handoff contract incomplete")

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

    for agent in agents:
        agent_id = agent["id"]
        agent_skills = set(agent.get("skills", []))
        prohibited = set(agent.get("prohibited_actions", []))
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

    return {
        "status": "AGENT_ECOSYSTEM_PASS",
        "agents": len(agents),
        "skills": len(skills),
        "acquisitions": len(acquisitions),
        "controlled_reference_acquisitions": acquired_count,
        "runtime_framework_dependencies": 0,
        "authority": agents_doc["authority"],
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
