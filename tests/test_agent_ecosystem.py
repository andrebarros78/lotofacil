from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_agent_ecosystem_validator_passes() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/validate_agent_ecosystem.py"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "AGENT_ECOSYSTEM_PASS"
    assert result["agents"] >= 8
    assert result["skills"] >= 20
    assert result["controlled_reference_acquisitions"] >= 3
    assert result["runtime_framework_dependencies"] == 0


def test_all_agents_are_bounded_by_canonical_branch_rules() -> None:
    agents = load_json("governance/agents/agents.json")["agents"]
    for agent in agents:
        prohibited = set(agent["prohibited_actions"])
        assert "direct_main_write" in prohibited
        assert "direct_operations_state_write" in prohibited
        assert agent["skills"]
        assert agent["allowed_actions"]


def test_scientific_agents_cannot_retune_lockbox() -> None:
    agents = {
        agent["id"]: agent
        for agent in load_json("governance/agents/agents.json")["agents"]
    }
    assert "lockbox_retuning" in agents["scientific-methodologist"]["prohibited_actions"]
    assert "lockbox_retuning" in agents["statistical-validator"]["prohibited_actions"]


def test_acquisitions_do_not_change_production_runtime() -> None:
    doc = load_json("governance/agents/acquisitions.json")
    assert doc["policy"]["production_core_must_remain_framework_independent_by_default"] is True
    assert all(item["runtime_dependency"] is False for item in doc["acquisitions"])


def test_critical_agent_roles_exist() -> None:
    agent_ids = {
        agent["id"]
        for agent in load_json("governance/agents/agents.json")["agents"]
    }
    assert {
        "chief-orchestrator",
        "scientific-methodologist",
        "statistical-validator",
        "data-provenance-auditor",
        "reproducibility-auditor",
        "security-tool-gate",
        "github-release-engineer",
        "operational-state-auditor",
        "agent-evaluator-redteam",
        "acquisition-scout",
    } <= agent_ids


def test_handoff_schema_matches_registry_contract() -> None:
    agents = load_json("governance/agents/agents.json")
    schema = load_json("governance/agents/handoff.schema.json")
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(agents["handoff_required_fields"])
    assert set(schema["required"]) <= set(schema["properties"])


def test_handoff_claim_levels_are_bounded() -> None:
    schema = load_json("governance/agents/handoff.schema.json")
    assert schema["properties"]["scientific_claim_level"]["enum"] == [
        "NONE",
        "DESCRIPTIVE",
        "RETROSPECTIVE",
        "SYNTHETIC_VALIDATION",
        "CONFIRMATORY_NOT_ESTABLISHED",
        "REPLICATED",
    ]
