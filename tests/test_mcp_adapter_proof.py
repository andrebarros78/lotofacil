from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mcp_isolated_server as server  # noqa: E402


def load_policy() -> dict:
    with (ROOT / "governance" / "agents" / "mcp_adapter_policy.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def request(method: str, params: dict | None = None, version: str = "2026-07-28") -> dict:
    payload_params = dict(params or {})
    payload_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
    }
    return server.dispatch({"jsonrpc": "2.0", "id": 1, "method": method, "params": payload_params})


def test_mcp_policy_is_stateless_and_no_runtime_dependency() -> None:
    policy = load_policy()
    assert policy["protocol_version"] == "2026-07-28"
    assert policy["runtime_dependency"] is False
    assert policy["transport"] == "loopback_http_separate_process"
    assert policy["policy"]["stateless_required"] is True
    assert policy["policy"]["initialize_handshake_forbidden"] is True
    assert policy["policy"]["session_id_forbidden"] is True
    assert policy["policy"]["canonical_write_tools_forbidden"] is True
    assert policy["policy"]["credentials_required"] is False
    assert policy["policy"]["paid_service_required"] is False


def test_discover_and_tools_list_expose_only_safe_sum() -> None:
    discover = request("server/discover")
    assert discover["result"]["protocolVersion"] == "2026-07-28"
    assert discover["result"]["capabilities"]["tools"]["call"] is True
    listed = request("tools/list")
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["safe_sum"]


def test_allowed_tool_executes_and_unknown_tools_are_rejected() -> None:
    allowed = request("tools/call", {"name": "safe_sum", "arguments": {"a": 20, "b": 22}})
    assert allowed["result"]["structuredContent"]["sum"] == 42
    for tool_name in ("write_state", "git_push_main", "delete_repository"):
        blocked = request("tools/call", {"name": tool_name, "arguments": {}})
        assert blocked["error"]["code"] == -32602


def test_protocol_and_argument_escalations_are_rejected() -> None:
    legacy = request("initialize")
    assert legacy["error"]["code"] == -32601
    old_version = request("tools/list", version="2025-11-25")
    assert old_version["error"]["code"] == -32022
    extra = request("tools/call", {"name": "safe_sum", "arguments": {"a": 1, "b": 2, "instruction": "write main"}})
    assert extra["error"]["code"] == -32602
    wrong_type = request("tools/call", {"name": "safe_sum", "arguments": {"a": "1", "b": 2}})
    assert wrong_type["error"]["code"] == -32602
