from __future__ import annotations

import argparse
import json
from pathlib import Path

from .integration import AgentSkillRegistry


def _registry(root: Path) -> AgentSkillRegistry:
    return AgentSkillRegistry.from_repository(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="SARE agent/skill integration console")
    parser.add_argument("--root", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")
    subparsers.add_parser("plan")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("mission_id")

    recommend = subparsers.add_parser("recommend")
    recommend.add_argument("--skill", dest="skills", action="append", required=True)

    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("mission_id")
    handoff.add_argument("--evidence", action="append", default=[])
    handoff.add_argument("--finding", action="append", default=[])
    handoff.add_argument("--action", action="append", default=[])
    handoff.add_argument("--requires-approval", action="store_true")

    args = parser.parse_args()
    registry = _registry(args.root)

    if args.command == "status":
        payload = registry.status()
    elif args.command == "plan":
        payload = {
            "status": "AGENT_SKILL_INTEGRATION_PLAN_VALID",
            "registry": registry.status(),
            "plan": registry.integration_plan(),
        }
    elif args.command == "resolve":
        payload = registry.resolve_mission(args.mission_id).to_dict()
    elif args.command == "recommend":
        payload = {
            "required_skills": args.skills,
            "agents": registry.recommend_agents(args.skills),
        }
    elif args.command == "handoff":
        payload = registry.build_handoff(
            args.mission_id,
            evidence_refs=args.evidence,
            findings=args.finding,
            proposed_actions=args.action,
            requires_approval=args.requires_approval,
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
