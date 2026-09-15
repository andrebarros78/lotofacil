from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "pr_pipeline_policy.json"


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("authority") != "GITHUB_ONLY":
        raise ValueError("authority drift")
    if policy.get("base_branch") != "main":
        raise ValueError("base branch must remain main")
    if policy.get("proposal_branch_prefix") != "agent-proof/":
        raise ValueError("unexpected proposal branch prefix")
    prefix = policy.get("proposal_path_prefix", "")
    if prefix != "sandbox/agent-pr-proof/":
        raise ValueError("proposal path must remain inside dedicated sandbox")
    if policy.get("allowed_files_per_proposal") != 1:
        raise ValueError("proof must remain single-file")
    if policy.get("direct_main_write_forbidden") is not True:
        raise ValueError("direct main write prohibition disabled")
    if policy.get("operations_state_write_forbidden") is not True:
        raise ValueError("operations/state write prohibition disabled")
    if policy.get("auto_merge_forbidden") is not True:
        raise ValueError("auto merge prohibition disabled")
    if policy.get("force_push_forbidden") is not True:
        raise ValueError("force push prohibition disabled")
    required = policy.get("required_workflow_dispatches")
    if required != ["ci.yml", "agent-capability-proof.yml", "agent-resilience-proof.yml"]:
        raise ValueError("required workflow set drift")
    for forbidden in policy.get("forbidden_path_prefixes", []):
        if prefix.startswith(forbidden) or forbidden.startswith(prefix):
            raise ValueError("sandbox overlaps forbidden prefix")


def build_proposal(source_sha: str, policy: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise ValueError("source SHA must be a lowercase 40-char git SHA")
    short = source_sha[:12]
    branch = f"{policy['proposal_branch_prefix']}{short}"
    path = f"{policy['proposal_path_prefix']}{short}.json"
    for forbidden in policy["forbidden_path_prefixes"]:
        if path.startswith(forbidden):
            raise ValueError(f"proposal path enters forbidden scope: {forbidden}")
    payload = {
        **policy["generated_payload_contract"],
        "proof_id": policy["proof_id"],
        "source_main_sha": source_sha,
        "proposal_branch": branch,
        "proposal_path": path,
        "authority": policy["authority"],
    }
    return branch, path, payload


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        self.token = token
        self.repo = repo
        self.base = f"https://api.github.com/repos/{repo}"

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "sare-bounded-agent-pr-proof",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {exc.code}: {body[:500]}") from exc

    def get_commit(self, sha: str) -> dict[str, Any]:
        return self.request("GET", f"/git/commits/{sha}")

    def create_blob(self, content: str) -> str:
        return self.request("POST", "/git/blobs", {"content": content, "encoding": "utf-8"})["sha"]

    def create_tree(self, base_tree: str, path: str, blob_sha: str) -> str:
        payload = {
            "base_tree": base_tree,
            "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}],
        }
        return self.request("POST", "/git/trees", payload)["sha"]

    def create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        payload = {"message": message, "tree": tree_sha, "parents": [parent_sha]}
        return self.request("POST", "/git/commits", payload)["sha"]

    def create_ref(self, branch: str, commit_sha: str) -> None:
        self.request("POST", "/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit_sha})

    def dispatch_workflow(self, workflow: str, branch: str) -> None:
        encoded = urllib.parse.quote(workflow, safe="")
        self.request("POST", f"/actions/workflows/{encoded}/dispatches", {"ref": branch})

    def workflow_runs(self, workflow: str, branch: str) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(workflow, safe="")
        query = urllib.parse.urlencode({"branch": branch, "event": "workflow_dispatch", "per_page": 20})
        payload = self.request("GET", f"/actions/workflows/{encoded}/runs?{query}")
        return payload.get("workflow_runs", [])

    def create_pull_request(self, title: str, body: str, branch: str, base: str) -> dict[str, Any]:
        return self.request("POST", "/pulls", {"title": title, "body": body, "head": branch, "base": base})


def wait_for_workflow(
    client: GitHubClient,
    workflow: str,
    branch: str,
    proposal_sha: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        matching = [run for run in client.workflow_runs(workflow, branch) if run.get("head_sha") == proposal_sha]
        if matching:
            run = max(matching, key=lambda item: item.get("id", 0))
            if run.get("status") == "completed":
                if run.get("conclusion") != "success":
                    raise RuntimeError(f"required workflow {workflow} concluded {run.get('conclusion')}")
                return {
                    "workflow": workflow,
                    "run_id": run["id"],
                    "status": run["status"],
                    "conclusion": run["conclusion"],
                    "head_sha": run["head_sha"],
                }
        time.sleep(poll_seconds)
    raise RuntimeError(f"timed out waiting for required workflow {workflow}")


def execute(output_path: Path) -> dict[str, Any]:
    policy = load_policy()
    validate_policy(policy)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    source_sha = os.environ.get("GITHUB_SHA", "")
    if not token or not repo or not source_sha:
        raise RuntimeError("GITHUB_TOKEN, GITHUB_REPOSITORY and GITHUB_SHA are required")

    branch, proposal_path, payload = build_proposal(source_sha, policy)
    client = GitHubClient(token, repo)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "AGENT_PR_PIPELINE_PROOF_FAIL",
        "proof_id": policy["proof_id"],
        "source_main_sha": source_sha,
        "proposal_branch": branch,
        "proposal_path": proposal_path,
        "policy_fingerprint_sha256": stable_sha(policy),
        "human_interventions": 0,
        "direct_main_writes": 0,
        "operations_state_writes": 0,
        "auto_merge_attempts": 0,
        "phase": "INIT",
        "required_workflows": [],
    }
    try:
        base_commit = client.get_commit(source_sha)
        base_tree = base_commit["tree"]["sha"]
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        blob_sha = client.create_blob(content)
        tree_sha = client.create_tree(base_tree, proposal_path, blob_sha)
        proposal_sha = client.create_commit(
            f"proof: bounded agent proposal from {source_sha[:12]}", tree_sha, source_sha
        )
        report.update({
            "phase": "COMMIT_CREATED",
            "proposal_commit_sha": proposal_sha,
            "proposal_parent_sha": source_sha,
            "proposal_blob_sha": blob_sha,
            "proposal_tree_sha": tree_sha,
            "payload_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
        client.create_ref(branch, proposal_sha)
        report["phase"] = "BRANCH_CREATED"

        for workflow in policy["required_workflow_dispatches"]:
            client.dispatch_workflow(workflow, branch)
        report["phase"] = "CHECKS_DISPATCHED"

        proof_runs: list[dict[str, Any]] = []
        for workflow in policy["required_workflow_dispatches"]:
            proof_runs.append(
                wait_for_workflow(
                    client,
                    workflow,
                    branch,
                    proposal_sha,
                    int(policy["workflow_timeout_seconds"]),
                    int(policy["poll_interval_seconds"]),
                )
            )
        report["required_workflows"] = proof_runs
        report["phase"] = "CHECKS_PASSED"

        pr_body = (
            "Bounded autonomous proposal-to-PR proof.\n\n"
            f"Source main SHA: `{source_sha}`\n"
            f"Proposal SHA: `{proposal_sha}`\n"
            f"Allowed path: `{proposal_path}`\n\n"
            "All predeclared workflow_dispatch checks completed successfully before this PR was created. "
            "This PR is evidence-only, requires human merge review, and MUST NOT be auto-merged."
        )
        pr = client.create_pull_request(
            f"[proof] bounded agent proposal {source_sha[:12]}",
            pr_body,
            branch,
            policy["base_branch"],
        )
        report.update({
            "phase": "PR_CREATED",
            "pull_request_number": pr["number"],
            "pull_request_url": pr["html_url"],
            "pull_request_state": pr["state"],
            "pull_request_merged": bool(pr.get("merged", False)),
            "status": "AGENT_PR_PIPELINE_PROOF_PASS",
        })
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove a bounded agent proposal-to-PR pipeline.")
    parser.add_argument("--output", default="artifacts/agent_pr_pipeline_proof.json")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--source-sha", default="0" * 40)
    args = parser.parse_args()
    policy = load_policy()
    validate_policy(policy)
    if args.plan:
        branch, path, payload = build_proposal(args.source_sha, policy)
        print(json.dumps({
            "status": "AGENT_PR_PIPELINE_PLAN_VALID",
            "branch": branch,
            "path": path,
            "payload": payload,
            "policy_fingerprint_sha256": stable_sha(policy),
        }, indent=2, sort_keys=True))
        return 0
    report = execute((ROOT / args.output).resolve())
    print(json.dumps({"status": report["status"], "phase": report["phase"]}, sort_keys=True))
    return 0 if report["status"] == "AGENT_PR_PIPELINE_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
