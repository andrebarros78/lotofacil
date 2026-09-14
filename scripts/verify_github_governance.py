from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "github-only-policy.json"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")


def main() -> int:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []
    notes: list[str] = []

    if policy.get("authority") != "GITHUB_ONLY":
        violations.append("authority must be GITHUB_ONLY")
    if policy.get("canonical_code_branch") != "main":
        violations.append("canonical code branch must be main")
    if policy.get("canonical_state_branch") != "operations/state":
        violations.append("canonical state branch must be operations/state")

    required = set(policy.get("required_workflows", []))
    existing = {str(path.relative_to(ROOT)).replace("\\", "/") for path in WORKFLOWS_DIR.glob("*.yml")}
    missing = sorted(required - existing)
    if missing:
        violations.append(f"missing required workflows: {missing}")

    write_workflows = set(policy.get("write_workflows", []))
    pinned = policy.get("pinned_actions", {})
    allowed_runners = set(policy.get("allowed_runners", []))

    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()

        if "self-hosted" in lowered:
            violations.append(f"{rel}: self-hosted runner is forbidden")

        for runner in re.findall(r"runs-on:\s*([^\n#]+)", text):
            runner = runner.strip().strip('"\'')
            if runner and runner not in allowed_runners:
                violations.append(f"{rel}: runner {runner!r} is not allowed")

        for action, ref in USES_RE.findall(text):
            if not SHA40.fullmatch(ref):
                violations.append(f"{rel}: action {action}@{ref} is not pinned to a 40-char SHA")
                continue
            expected = pinned.get(action)
            if expected and ref != expected:
                violations.append(f"{rel}: action {action} SHA differs from governance policy")

        has_write = bool(re.search(r"(?m)^\s*contents:\s*write\s*$", text))
        if has_write and rel not in write_workflows:
            violations.append(f"{rel}: contents:write is not authorized")
        if rel in write_workflows and not has_write:
            violations.append(f"{rel}: authorized writer must explicitly declare contents:write")

    operations_path = ROOT / ".github" / "workflows" / "github-operations.yml"
    if operations_path.exists():
        text = operations_path.read_text(encoding="utf-8")
        required_markers = [
            "workflow_dispatch:",
            "schedule:",
            "ref: main",
            "ref: operations/state",
            "cancel-in-progress: false",
            "verify_github_operational_state.py",
            "git push origin HEAD:operations/state",
            "committed-state-audit:",
        ]
        for marker in required_markers:
            if marker not in text:
                violations.append(f"github-operations.yml missing marker: {marker}")

    operator_path = ROOT / ".github" / "workflows" / "operator-console.yml"
    if operator_path.exists():
        text = operator_path.read_text(encoding="utf-8")
        if "workflow_dispatch:" not in text:
            violations.append("operator-console.yml must be manually dispatchable")
        if re.search(r"(?m)^\s*contents:\s*write\s*$", text):
            violations.append("operator-console.yml must remain read-only")
        if "ref: operations/state" not in text:
            violations.append("operator-console.yml must read the canonical operations/state branch")

    proof_path = ROOT / ".github" / "workflows" / "operator-console-proof.yml"
    if proof_path.exists():
        text = proof_path.read_text(encoding="utf-8")
        proof_markers = [
            "workflow_dispatch:",
            "push:",
            "ref: main",
            "ref: operations/state",
            "--action status",
            "--action audit",
            "--action analyze",
            "--action portfolio",
            "--action export",
            "SARE_OPERATOR_CONSOLE_PROOF_PASS",
            "operations_state_sha",
        ]
        for marker in proof_markers:
            if marker not in text:
                violations.append(f"operator-console-proof.yml missing marker: {marker}")
        if re.search(r"(?m)^\s*contents:\s*write\s*$", text):
            violations.append("operator-console-proof.yml must remain read-only")

    native = policy.get("native_ruleset", {})
    if native.get("status") != "ENFORCED":
        notes.append("NATIVE_RULESET_PENDING_EXTERNAL_ADMIN_ACTION")

    payload = {
        "status": "GITHUB_GOVERNANCE_PASS" if not violations else "GITHUB_GOVERNANCE_FAIL",
        "violations": violations,
        "notes": notes,
        "authority": policy.get("authority"),
        "canonical_code_branch": policy.get("canonical_code_branch"),
        "canonical_state_branch": policy.get("canonical_state_branch"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
