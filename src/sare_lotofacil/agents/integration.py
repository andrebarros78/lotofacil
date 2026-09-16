from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ResolvedMission:
    mission: dict[str, Any]
    agent: dict[str, Any]
    required_skills: tuple[dict[str, Any], ...]
    agent_skills: tuple[dict[str, Any], ...]
    tool: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission,
            "agent": self.agent,
            "required_skills": list(self.required_skills),
            "agent_skills": list(self.agent_skills),
            "tool": self.tool,
        }


class AgentSkillRegistry:
    """Deterministic resolver binding SARE agents, skills, missions and tools.

    The registry is read-only. It loads only versioned repository contracts and never
    performs tool execution or canonical writes itself.
    """

    def __init__(
        self,
        *,
        root: Path,
        agents_doc: dict[str, Any],
        skills_doc: dict[str, Any],
        missions_doc: dict[str, Any],
        tools_doc: dict[str, Any],
    ) -> None:
        self.root = root.resolve()
        self.agents_doc = agents_doc
        self.skills_doc = skills_doc
        self.missions_doc = missions_doc
        self.tools_doc = tools_doc
        self._validate()

        self.agents = {item["id"]: item for item in agents_doc["agents"]}
        self.skills = {item["id"]: item for item in skills_doc["skills"]}
        self.missions = {item["id"]: item for item in missions_doc["missions"]}
        self.tools = {item["id"]: item for item in tools_doc["tools"]}

    @classmethod
    def from_repository(cls, root: Path) -> "AgentSkillRegistry":
        root = root.resolve()
        base = root / "governance" / "agents"

        def load(name: str) -> dict[str, Any]:
            with (base / name).open("r", encoding="utf-8") as handle:
                return json.load(handle)

        return cls(
            root=root,
            agents_doc=load("agents.json"),
            skills_doc=load("skills.json"),
            missions_doc=load("capability_missions.json"),
            tools_doc=load("tool_bindings.json"),
        )

    @staticmethod
    def _unique(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{label} without id")
            if item_id in result:
                raise ValueError(f"duplicate {label} id: {item_id}")
            result[item_id] = item
        return result

    def _validate(self) -> None:
        for label, doc in (
            ("agents", self.agents_doc),
            ("skills", self.skills_doc),
            ("missions", self.missions_doc),
            ("tools", self.tools_doc),
        ):
            if doc.get("schema_version") != 1:
                raise ValueError(f"unsupported {label} schema")

        if self.agents_doc.get("authority") != "GITHUB_ONLY":
            raise ValueError("agent authority drift")
        if self.missions_doc.get("authority") != "GITHUB_ONLY":
            raise ValueError("mission authority drift")
        if self.missions_doc.get("runtime_framework") != "NONE":
            raise ValueError("external runtime framework is not canonical")

        agents = self._unique(self.agents_doc.get("agents", []), "agent")
        skills = self._unique(self.skills_doc.get("skills", []), "skill")
        missions = self._unique(self.missions_doc.get("missions", []), "mission")
        tools = self._unique(self.tools_doc.get("tools", []), "tool")

        assigned_skill_ids: set[str] = set()
        for agent_id, agent in agents.items():
            agent_skills = agent.get("skills")
            if not isinstance(agent_skills, list) or not agent_skills:
                raise ValueError(f"agent without skills: {agent_id}")
            unknown = sorted(set(agent_skills) - set(skills))
            if unknown:
                raise ValueError(f"agent {agent_id} has unknown skills: {unknown}")
            assigned_skill_ids.update(agent_skills)

        unassigned = sorted(set(skills) - assigned_skill_ids)
        if unassigned:
            raise ValueError(f"catalog skills without an agent: {unassigned}")

        mission_bound_agents: set[str] = set()
        for mission_id, mission in missions.items():
            agent_id = mission.get("agent_id")
            tool_id = mission.get("tool_id")
            required_skills = mission.get("required_skills")
            if agent_id not in agents:
                raise ValueError(f"mission {mission_id} references unknown agent: {agent_id}")
            if tool_id not in tools:
                raise ValueError(f"mission {mission_id} references unknown tool: {tool_id}")
            if not isinstance(required_skills, list) or not required_skills:
                raise ValueError(f"mission {mission_id} has no required_skills")
            unknown_required = sorted(set(required_skills) - set(skills))
            if unknown_required:
                raise ValueError(
                    f"mission {mission_id} requires unknown skills: {unknown_required}"
                )
            missing = sorted(set(required_skills) - set(agents[agent_id]["skills"]))
            if missing:
                raise ValueError(
                    f"mission {mission_id} assigned to {agent_id} lacks skills: {missing}"
                )
            mission_bound_agents.add(agent_id)

        unbound_agents = sorted(set(agents) - mission_bound_agents)
        if unbound_agents:
            raise ValueError(f"agents without executable mission binding: {unbound_agents}")

        policy = self.missions_doc.get("mission_policy", {})
        if policy.get("direct_main_write_forbidden") is not True:
            raise ValueError("direct main write prohibition disabled")
        if policy.get("direct_operations_state_write_forbidden") is not True:
            raise ValueError("direct operations/state write prohibition disabled")
        if self.tools_doc.get("policy", {}).get("write_effects_forbidden") is not True:
            raise ValueError("tool write-effect prohibition disabled")

    def resolve_mission(self, mission_id: str) -> ResolvedMission:
        mission = self.missions.get(mission_id)
        if mission is None:
            raise KeyError(f"unknown mission: {mission_id}")
        agent = self.agents[mission["agent_id"]]
        required = tuple(self.skills[skill_id] for skill_id in mission["required_skills"])
        agent_skills = tuple(self.skills[skill_id] for skill_id in agent["skills"])
        tool = self.tools[mission["tool_id"]]
        return ResolvedMission(
            mission=mission,
            agent=agent,
            required_skills=required,
            agent_skills=agent_skills,
            tool=tool,
        )

    def recommend_agents(self, required_skills: Iterable[str]) -> list[dict[str, Any]]:
        required = tuple(dict.fromkeys(required_skills))
        unknown = sorted(set(required) - set(self.skills))
        if unknown:
            raise KeyError(f"unknown skills: {unknown}")
        required_set = set(required)
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for agent_id, agent in self.agents.items():
            owned = set(agent["skills"])
            coverage = len(required_set & owned)
            if required_set.issubset(owned):
                ranked.append((coverage, agent_id, agent))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            {
                "agent_id": agent_id,
                "role": agent["role"],
                "required_skills": list(required),
                "matched_skills": sorted(required_set & set(agent["skills"])),
                "allowed_actions": agent["allowed_actions"],
                "prohibited_actions": agent["prohibited_actions"],
            }
            for _, agent_id, agent in ranked
        ]

    def integration_plan(self) -> list[dict[str, Any]]:
        return [
            self.resolve_mission(mission_id).to_dict()
            for mission_id in sorted(self.missions)
        ]

    def build_handoff(
        self,
        mission_id: str,
        *,
        evidence_refs: Iterable[str],
        findings: Iterable[str],
        proposed_actions: Iterable[str] = (),
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        resolved = self.resolve_mission(mission_id)
        mission = resolved.mission
        return {
            "agent_id": resolved.agent["id"],
            "task_id": mission_id,
            "evidence_refs": list(evidence_refs),
            "findings": list(findings),
            "proposed_actions": list(proposed_actions),
            "risk_level": mission["risk_level"],
            "requires_approval": bool(requires_approval),
            "scientific_claim_level": mission["scientific_claim_level"],
        }

    def status(self) -> dict[str, Any]:
        assigned_skills = {
            skill_id
            for agent in self.agents.values()
            for skill_id in agent["skills"]
        }
        mission_bound_agents = {mission["agent_id"] for mission in self.missions.values()}
        material = {
            "agents": self.agents_doc,
            "skills": self.skills_doc,
            "missions": self.missions_doc,
            "tools": self.tools_doc,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "status": "AGENT_SKILL_INTEGRATION_VALID",
            "authority": "GITHUB_ONLY",
            "runtime_framework": "NONE",
            "read_only": True,
            "agents": len(self.agents),
            "skills": len(self.skills),
            "missions": len(self.missions),
            "tools": len(self.tools),
            "agents_with_mission_binding": len(mission_bound_agents),
            "skills_assigned_to_agents": len(assigned_skills),
            "all_agents_bound": len(mission_bound_agents) == len(self.agents),
            "all_skills_assigned": len(assigned_skills) == len(self.skills),
            "registry_fingerprint_sha256": fingerprint,
        }
