from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_JOB_IDS = ("ci", "scientific", "operational", "security", "release-candidate")


def verify(root: Path) -> dict[str, object]:
    contract_path = root / "governance" / "merge-gates.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    workflow_path = root / str(contract["workflow"])
    workflow = workflow_path.read_text(encoding="utf-8")

    violations: list[str] = []
    required_checks = tuple(str(item) for item in contract["required_status_checks"])
    for check in required_checks:
        if not re.search(rf"^    name: {re.escape(check)}\s*$", workflow, re.MULTILINE):
            violations.append(f"MISSING_STABLE_CHECK:{check}")

    for job_id in REQUIRED_JOB_IDS:
        if not re.search(rf"^  {re.escape(job_id)}:\s*$", workflow, re.MULTILINE):
            violations.append(f"MISSING_JOB_ID:{job_id}")

    expected_needs = tuple(str(item) for item in contract["release_candidate_depends_on"])
    expected_needs_literal = "needs: [" + ", ".join(expected_needs) + "]"
    release_match = re.search(
        r"^  release-candidate:\s*$([\s\S]*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
        workflow,
        re.MULTILINE,
    )
    if release_match is None:
        violations.append("MISSING_RELEASE_CANDIDATE_JOB")
    elif expected_needs_literal not in release_match.group(1):
        violations.append("RELEASE_CANDIDATE_DEPENDENCIES_MISMATCH")

    if contract.get("enforcement_required") is not True:
        violations.append("RULESET_ENFORCEMENT_NOT_REQUIRED_BY_CONTRACT")
    if contract.get("ruleset_target") != "refs/heads/main":
        violations.append("RULESET_TARGET_MISMATCH")

    return {
        "status": "MERGE_GATES_CONTRACT_PASS" if not violations else "MERGE_GATES_CONTRACT_FAIL",
        "required_status_checks": list(required_checks),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = verify(args.root.resolve())
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "MERGE_GATES_CONTRACT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
