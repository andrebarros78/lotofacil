from __future__ import annotations

import json
from pathlib import Path

import scripts.mcp_authenticated_external_server as server

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def request(method: str, *, name: str | None = None, arguments=None, protocol: str | None = None) -> dict:
    version = protocol or server.PROTOCOL_VERSION
    params: dict = {"_meta": {"io.modelcontextprotocol/protocolVersion": version}}
    if name is not None:
        params["name"] = name
        params["arguments"] = arguments
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


def test_a06_external_policy_is_bounded_and_predeclared() -> None:
    policy = load_json("governance/agents/mcp_external_authenticated_policy.json")
    acceptance = policy["acceptance"]
    claims = policy["claim_boundary"]
    assert policy["proof_id"] == "EXTERNAL-MCP-AUTHENTICATED-GITHUB-BOUNDED-V1"
    assert policy["gap_id"] == "GAP-A06"
    assert policy["protocol_version"] == "2026-07-28"
    assert policy["authority"] == "GITHUB_ONLY"
    assert policy["runtime_framework"] == "NONE"
    assert policy["provider"]["api_origin"] == "https://api.github.com"
    assert policy["provider"]["repository_allowlist"] == ["andrebarros78/lotofacil"]
    assert policy["provider"]["provider_http_methods"] == ["GET"]
    assert policy["oidc"]["audience"] == "sare-lotofacil-gap-a06"
    assert policy["policy"]["provider_write_requests_forbidden"] is True
    assert policy["policy"]["arbitrary_url_forbidden"] is True
    assert policy["policy"]["arbitrary_repository_forbidden"] is True
    assert policy["policy"]["direct_main_write_forbidden"] is True
    assert policy["policy"]["direct_operations_state_write_forbidden"] is True
    assert policy["policy"]["benchmark_mutation_after_first_result_forbidden"] is True
    assert acceptance["benchmark_cases"] == 14
    assert acceptance["required_pass_rate"] == 1.0
    assert acceptance["max_provider_write_requests"] == 0
    assert acceptance["max_credential_exposures"] == 0
    assert claims["allowed_status_if_pass"] == "PROVEN_FOR_BOUNDED_AUTHENTICATED_EXTERNAL_MCP_READ_ONLY_GITHUB_PROVIDER"
    assert claims["arbitrary_third_party_mcp_provider_proven"] is False
    assert claims["write_capable_external_mcp_proven"] is False
    assert claims["production_mutation_authority_granted"] is False
    assert claims["arbitrary_network_authority_granted"] is False
    assert claims["general_oauth_provider_interoperability_proven"] is False


def test_a06_benchmark_is_frozen_and_unique() -> None:
    benchmark = load_json("governance/agents/mcp_external_authenticated_benchmark.json")
    cases = benchmark["cases"]
    ids = [case["id"] for case in cases]
    assert benchmark["frozen_before_implementation"] is True
    assert len(cases) == 14
    assert len(ids) == len(set(ids))
    assert ids == [f"A06-{index:02d}" for index in range(1, 15)]


def test_a06_tool_surface_is_exact_and_argument_free() -> None:
    policy = load_json("governance/agents/mcp_external_authenticated_policy.json")
    tools = policy["allowed_tools"]
    assert [tool["name"] for tool in tools] == ["github_repo_metadata", "github_oidc_identity"]
    for tool in tools:
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert schema["required"] == []
        assert schema["additionalProperties"] is False
        assert schema["properties"] == {}


def test_a06_discovery_and_listing_match_frozen_contract() -> None:
    discover = server.dispatch(request("server/discover"))
    assert discover["result"]["protocolVersion"] == "2026-07-28"
    listed = server.dispatch(request("tools/list"))
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["github_repo_metadata", "github_oidc_identity"]


def test_a06_rejects_protocol_legacy_initialize_and_write_tool() -> None:
    old = server.dispatch(request("server/discover", protocol="2025-11-25"))
    assert old["error"]["message"] == "UnsupportedProtocolVersion"
    initialize = server.dispatch(request("initialize"))
    assert initialize["error"]["code"] == -32601
    write = server.dispatch(request("tools/call", name="github_write_file", arguments={}))
    assert write["error"]["code"] == -32602


def test_a06_rejects_repository_url_and_invalid_argument_types_without_provider_call(monkeypatch) -> None:
    calls = {"repo": 0}

    def should_not_call() -> dict:
        calls["repo"] += 1
        return {"full_name": "andrebarros78/lotofacil"}

    monkeypatch.setattr(server, "github_repo_metadata", should_not_call)
    repository = server.dispatch(request("tools/call", name="github_repo_metadata", arguments={"repository": "other/repo"}))
    url = server.dispatch(request("tools/call", name="github_repo_metadata", arguments={"url": "https://example.com"}))
    invalid = server.dispatch(request("tools/call", name="github_repo_metadata", arguments=[]))
    assert repository["error"]["code"] == -32602
    assert url["error"]["code"] == -32602
    assert invalid["error"]["code"] == -32602
    assert calls["repo"] == 0


def test_a06_allowed_tools_return_only_sanitized_stubbed_content(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "github_repo_metadata",
        lambda: {"full_name": "andrebarros78/lotofacil", "default_branch": "main", "private": False},
    )
    monkeypatch.setattr(
        server,
        "github_oidc_identity",
        lambda: {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "sare-lotofacil-gap-a06",
            "repository": "andrebarros78/lotofacil",
            "actor": "andrebarros78",
        },
    )
    repo = server.dispatch(request("tools/call", name="github_repo_metadata", arguments={}))
    oidc = server.dispatch(request("tools/call", name="github_oidc_identity", arguments={}))
    assert repo["result"]["structuredContent"]["full_name"] == "andrebarros78/lotofacil"
    assert oidc["result"]["structuredContent"]["aud"] == "sare-lotofacil-gap-a06"
    serialized = json.dumps([repo, oidc])
    assert "ACTIONS_ID_TOKEN_REQUEST_TOKEN" not in serialized
    assert "GITHUB_TOKEN" not in serialized


def test_a06_registry_records_canonical_bounded_proof_without_claim_inflation() -> None:
    gaps = {item["id"]: item for item in load_json("governance/agents/capability_gaps.json")["gaps"]}
    assert gaps["GAP-A06"]["status"] == "PROVEN_FOR_BOUNDED_AUTHENTICATED_EXTERNAL_MCP_READ_ONLY_GITHUB_PROVIDER"

    record = load_json("governance/agents/external_mcp_authenticated_proof_history.json")["proofs"][-1]
    assert record["decision"] == "PROVEN_FOR_BOUNDED_AUTHENTICATED_EXTERNAL_MCP_READ_ONLY_GITHUB_PROVIDER"
    assert record["prior_status"] == "PARTIALLY_PROVEN_ISOLATED_STATELESS_ADAPTER_ONLY"
    assert record["policy_commit_sha"] == "284cc9cde8846fbe08555fc607c95adebdc4f297"
    assert record["benchmark_frozen_commit_sha"] == "255278909f405664863bb5b9320ed8dbd383f6dd"
    assert record["predeclaration_main_sha"] == "fbf92bf9a45ac17a8ba8fe3064c895d62f249e83"
    assert record["canonical_main_sha"] == "842c5383a61c7dbec383a2a4868c224aeb0e670b"
    assert record["workflow_run_id"] == 35027266769
    assert record["artifact_id"] == 10419288586
    assert record["artifact_digest"] == "sha256:a166401e1bae0585be4cb01ab4ffd3ff5050dd3871ba297aeeb339673a765d99"
    assert record["metrics"]["checks_passed"] == 14
    assert record["metrics"]["authenticated_external_https_calls"] == 2
    assert record["metrics"]["github_api_authenticated_reads"] == 1
    assert record["metrics"]["oidc_flows"] == 1
    assert record["metrics"]["unauthorized_successes"] == 0
    assert record["metrics"]["arbitrary_target_successes"] == 0
    assert record["metrics"]["provider_write_requests"] == 0
    assert record["metrics"]["canonical_write_tools_exposed"] == 0
    assert record["metrics"]["credential_exposures"] == 0
    assert record["governance_effect"]["authenticated_external_provider_tool_execution_proven"] is True
    assert record["governance_effect"]["github_actions_oidc_flow_proven"] is True
    assert record["governance_effect"]["arbitrary_third_party_mcp_provider_proven"] is False
    assert record["governance_effect"]["write_capable_external_mcp_proven"] is False
    assert record["governance_effect"]["production_mutation_authority_granted"] is False
    assert record["governance_effect"]["arbitrary_network_authority_granted"] is False
    assert record["governance_effect"]["general_oauth_provider_interoperability_proven"] is False
