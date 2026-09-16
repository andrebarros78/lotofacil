from __future__ import annotations

from pathlib import Path

import pytest

from sare_lotofacil.agents import AgentSkillRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_registry_integrates_all_agents_and_skills() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)
    status = registry.status()

    assert status["status"] == "AGENT_SKILL_INTEGRATION_VALID"
    assert status["authority"] == "GITHUB_ONLY"
    assert status["runtime_framework"] == "NONE"
    assert status["read_only"] is True
    assert status["agents"] == 12
    assert status["skills"] == 30
    assert status["missions"] == 12
    assert status["all_agents_bound"] is True
    assert status["all_skills_assigned"] is True
    assert status["agents_with_mission_binding"] == status["agents"]
    assert status["skills_assigned_to_agents"] == status["skills"]
    assert len(status["registry_fingerprint_sha256"]) == 64


def test_every_mission_is_skill_satisfied_by_its_agent() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)

    for mission_id in registry.missions:
        resolved = registry.resolve_mission(mission_id)
        required = {skill["id"] for skill in resolved.required_skills}
        owned = {skill["id"] for skill in resolved.agent_skills}
        assert required
        assert required <= owned
        assert resolved.tool["id"] == resolved.mission["tool_id"]


def test_rag_retrieval_mission_resolves_dedicated_specialist() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)
    resolved = registry.resolve_mission("CAP-011-rag-retrieval-integration")

    assert resolved.agent["id"] == "rag-retrieval-engineer"
    assert resolved.tool["id"] == "rag_tests"
    assert {skill["id"] for skill in resolved.required_skills} == {
        "rag_retrieval_quality",
        "source_authority_ranking",
        "rag_corpus_governance",
        "evidence_hashing",
        "github_actions",
    }


def test_recommend_agents_requires_full_skill_coverage() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)
    recommendations = registry.recommend_agents(
        ["rag_grounding_evaluation", "prompt_injection_defense"]
    )

    assert recommendations
    assert recommendations[0]["agent_id"] == "rag-evaluation-redteam"
    assert set(recommendations[0]["matched_skills"]) == {
        "rag_grounding_evaluation",
        "prompt_injection_defense",
    }


def test_recommend_agents_rejects_unknown_skill() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)

    with pytest.raises(KeyError, match="unknown skills"):
        registry.recommend_agents(["skill-that-does-not-exist"])


def test_handoff_is_generated_from_resolved_mission_contract() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)
    handoff = registry.build_handoff(
        "CAP-009-orchestrator-skill-routing",
        evidence_refs=["proof:agent-skill-integration"],
        findings=["routing contract valid"],
        proposed_actions=[],
    )

    assert handoff == {
        "agent_id": "chief-orchestrator",
        "task_id": "CAP-009-orchestrator-skill-routing",
        "evidence_refs": ["proof:agent-skill-integration"],
        "findings": ["routing contract valid"],
        "proposed_actions": [],
        "risk_level": "LOW",
        "requires_approval": False,
        "scientific_claim_level": "NONE",
    }


def test_integration_plan_covers_each_agent_once_or_more() -> None:
    registry = AgentSkillRegistry.from_repository(ROOT)
    plan = registry.integration_plan()
    bound = {item["agent"]["id"] for item in plan}

    assert len(plan) == 12
    assert bound == set(registry.agents)
