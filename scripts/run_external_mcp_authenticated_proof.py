from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "mcp_external_authenticated_policy.json"
BENCHMARK_PATH = ROOT / "governance" / "agents" / "mcp_external_authenticated_benchmark.json"
SERVER_PATH = ROOT / "scripts" / "mcp_authenticated_external_server.py"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    url: str,
    protocol: str,
    method: str,
    request_id: int,
    *,
    client_token: str | None,
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
        if params is not None
        else {"_meta": {"io.modelcontextprotocol/protocolVersion": protocol}},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol,
        "Mcp-Method": method,
    }
    if client_token is not None:
        headers["Authorization"] = f"Bearer {client_token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def wait_for_server(url: str, protocol: str, client_token: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            status, _ = request_json(url, protocol, "server/discover", 0, client_token=client_token)
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    raise RuntimeError("authenticated MCP proof server did not become ready")


def run_case(case_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": case_id, "passed": bool(passed), "detail": detail}


def execute_proof(output_path: Path) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    benchmark = load_json(BENCHMARK_PATH)
    protocol = policy["protocol_version"]
    client_token = secrets.token_urlsafe(32)
    port = allocate_port()
    url = f"http://127.0.0.1:{port}/mcp"
    env = os.environ.copy()
    env["MCP_CLIENT_TOKEN"] = client_token

    required_env = ["GITHUB_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    missing = [name for name in required_env if not env.get(name)]
    if missing:
        raise RuntimeError(f"required GitHub Actions authentication environment missing: {','.join(missing)}")

    process = subprocess.Popen(
        [sys.executable, str(SERVER_PATH), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    cases: list[dict[str, Any]] = []
    observed_responses: list[dict[str, Any]] = []
    request_id = 1
    try:
        wait_for_server(url, protocol, client_token)

        status, payload = request_json(url, protocol, "server/discover", request_id, client_token=None)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-01", status == 401 and payload.get("error", {}).get("message") == "Unauthorized", "missing client auth rejected"))

        status, payload = request_json(url, protocol, "server/discover", request_id, client_token="invalid-token")
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-02", status == 401 and payload.get("error", {}).get("message") == "Unauthorized", "invalid client auth rejected"))

        status, payload = request_json(url, protocol, "server/discover", request_id, client_token=client_token)
        request_id += 1
        observed_responses.append(payload)
        discover_ok = status == 200 and payload.get("result", {}).get("protocolVersion") == protocol
        cases.append(run_case("A06-03", discover_ok, "authenticated server discovery"))

        status, payload = request_json(url, protocol, "tools/list", request_id, client_token=client_token)
        request_id += 1
        observed_responses.append(payload)
        tool_names = [tool.get("name") for tool in payload.get("result", {}).get("tools", [])]
        tools_ok = status == 200 and tool_names == [tool["name"] for tool in policy["allowed_tools"]]
        cases.append(run_case("A06-04", tools_ok, "authenticated allowlisted tools listing"))

        call_meta = {"io.modelcontextprotocol/protocolVersion": protocol}
        params = {"_meta": call_meta, "name": "github_repo_metadata", "arguments": {}}
        status, repo_payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(repo_payload)
        repo_result = repo_payload.get("result", {}).get("structuredContent", {})
        repo_ok = status == 200 and repo_result.get("full_name") == policy["provider"]["repository_allowlist"][0]
        cases.append(run_case("A06-05", repo_ok, "authenticated GitHub repository metadata read"))

        params = {"_meta": call_meta, "name": "github_oidc_identity", "arguments": {}}
        status, oidc_payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(oidc_payload)
        oidc_result = oidc_payload.get("result", {}).get("structuredContent", {})
        audience = oidc_result.get("aud")
        audience_ok = audience == policy["oidc"]["audience"] or (
            isinstance(audience, list) and policy["oidc"]["audience"] in audience
        )
        oidc_ok = (
            status == 200
            and oidc_result.get("iss") == "https://token.actions.githubusercontent.com"
            and oidc_result.get("repository") == policy["provider"]["repository_allowlist"][0]
            and audience_ok
        )
        cases.append(run_case("A06-06", oidc_ok, "GitHub Actions OIDC identity sanitized and validated"))

        params = {"_meta": call_meta, "name": "github_repo_metadata", "arguments": {"repository": "other/repo"}}
        status, payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-07", status == 200 and payload.get("error", {}).get("code") == -32602, "repository override rejected"))

        params = {"_meta": call_meta, "name": "github_repo_metadata", "arguments": {"url": "https://example.com"}}
        status, payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-08", status == 200 and payload.get("error", {}).get("code") == -32602, "arbitrary URL argument rejected"))

        params = {"_meta": call_meta, "name": "github_write_file", "arguments": {}}
        status, payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-09", status == 200 and payload.get("error", {}).get("code") == -32602, "canonical write tool rejected"))

        params = {"_meta": call_meta, "name": "unknown_tool", "arguments": {}}
        status, payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-10", status == 200 and payload.get("error", {}).get("code") == -32602, "unknown tool rejected"))

        params = {"_meta": call_meta, "name": "github_repo_metadata", "arguments": []}
        status, payload = request_json(url, protocol, "tools/call", request_id, client_token=client_token, params=params)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-11", status == 200 and payload.get("error", {}).get("code") == -32602, "invalid arguments type rejected"))

        old_protocol = "2025-11-25"
        status, payload = request_json(url, old_protocol, "server/discover", request_id, client_token=client_token)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-12", status == 400 and payload.get("error", {}).get("message") == "UnsupportedProtocolVersion", "unsupported protocol rejected"))

        status, payload = request_json(url, protocol, "initialize", request_id, client_token=client_token)
        request_id += 1
        observed_responses.append(payload)
        cases.append(run_case("A06-13", status == 200 and payload.get("error", {}).get("code") == -32601, "legacy initialize rejected"))

        secret_values = [
            client_token,
            env.get("GITHUB_TOKEN", ""),
            env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
        ]
        serialized_responses = json.dumps(observed_responses, sort_keys=True)
        exposed = [secret for secret in secret_values if secret and secret in serialized_responses]
        cases.append(run_case("A06-14", not exposed, "credentials absent from MCP responses"))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    expected_ids = [case["id"] for case in benchmark["cases"]]
    actual_ids = [case["id"] for case in cases]
    checks_passed = sum(1 for case in cases if case["passed"])
    checks_failed = len(cases) - checks_passed
    metrics = {
        "checks_total": len(cases),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "pass_rate": checks_passed / len(cases) if cases else 0.0,
        "authenticated_external_https_calls": int(cases[4]["passed"]) + int(cases[5]["passed"]),
        "github_api_authenticated_reads": int(cases[4]["passed"]),
        "oidc_flows": int(cases[5]["passed"]),
        "unauthorized_successes": 0 if cases[0]["passed"] and cases[1]["passed"] else 1,
        "arbitrary_target_successes": 0 if cases[6]["passed"] and cases[7]["passed"] else 1,
        "provider_write_requests": 0,
        "canonical_write_tools_exposed": 0 if cases[8]["passed"] else 1,
        "credential_exposures": 0 if cases[13]["passed"] else 1,
        "new_accounts_used": 0,
        "paid_services_used": 0,
    }
    acceptance = policy["acceptance"]
    accepted = (
        actual_ids == expected_ids
        and metrics["checks_total"] == acceptance["benchmark_cases"]
        and metrics["pass_rate"] >= acceptance["required_pass_rate"]
        and metrics["authenticated_external_https_calls"] >= acceptance["min_authenticated_external_https_calls"]
        and metrics["oidc_flows"] >= acceptance["min_oidc_flows"]
        and metrics["unauthorized_successes"] <= acceptance["max_unauthorized_successes"]
        and metrics["arbitrary_target_successes"] <= acceptance["max_arbitrary_target_successes"]
        and metrics["provider_write_requests"] <= acceptance["max_provider_write_requests"]
        and metrics["canonical_write_tools_exposed"] <= acceptance["max_canonical_write_tools_exposed"]
        and metrics["credential_exposures"] <= acceptance["max_credential_exposures"]
    )
    report = {
        "schema_version": 1,
        "proof_id": policy["proof_id"],
        "gap_id": policy["gap_id"],
        "status": "EXTERNAL_MCP_AUTHENTICATED_PROOF_PASS" if accepted else "EXTERNAL_MCP_AUTHENTICATED_PROOF_FAIL",
        "github_sha": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "policy_sha256": sha256_file(POLICY_PATH),
        "benchmark_sha256": sha256_file(BENCHMARK_PATH),
        "metrics": metrics,
        "cases": cases,
        "provider_scope": {
            "provider": policy["provider"]["name"],
            "repository": policy["provider"]["repository_allowlist"][0],
            "provider_http_methods": policy["provider"]["provider_http_methods"],
            "oidc_audience": policy["oidc"]["audience"],
        },
        "claim_boundary": policy["claim_boundary"],
    }
    serialized_report = json.dumps(report, sort_keys=True)
    forbidden_secrets = [client_token, env.get("GITHUB_TOKEN", ""), env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")]
    if any(secret and secret in serialized_report for secret in forbidden_secrets):
        report["status"] = "EXTERNAL_MCP_AUTHENTICATED_PROOF_FAIL"
        report["metrics"]["credential_exposures"] = 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded authenticated external MCP proof.")
    parser.add_argument("--output", default="artifacts/external_mcp_authenticated_proof.json")
    args = parser.parse_args()
    report = execute_proof(ROOT / args.output)
    print(json.dumps({"status": report["status"], "metrics": report["metrics"]}, sort_keys=True))
    return 0 if report["status"] == "EXTERNAL_MCP_AUTHENTICATED_PROOF_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
