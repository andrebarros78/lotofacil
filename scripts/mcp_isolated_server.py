from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "mcp_adapter_policy.json"


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


POLICY = load_policy()
PROTOCOL_VERSION = POLICY["protocol_version"]
TOOLS = {tool["name"]: tool for tool in POLICY["allowed_tools"]}


def meta() -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/serverInfo": {
            "name": "sare-isolated-mcp-proof",
            "version": "1.0",
        },
    }


def result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    payload.setdefault("_meta", meta())
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error_response(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def validate_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be integer")
    if not -1_000_000 <= value <= 1_000_000:
        raise ValueError(f"{field} outside allowed range")
    return value


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    request_meta = params.get("_meta") if isinstance(params, dict) else None
    if not isinstance(request_meta, dict):
        return error_response(request_id, -32602, "missing request _meta")
    if request_meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION:
        return error_response(
            request_id,
            -32022,
            "UnsupportedProtocolVersion",
            {"supported": [PROTOCOL_VERSION]},
        )
    if method == "initialize" or method == "notifications/initialized":
        return error_response(request_id, -32601, "Method not supported by MCP 2026-07-28")
    if method == "server/discover":
        return result_response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "sare-isolated-mcp-proof", "version": "1.0"},
                "capabilities": {"tools": {"list": True, "call": True}},
            },
        )
    if method == "tools/list":
        return result_response(request_id, {"tools": list(TOOLS.values())})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if name not in TOOLS:
            return error_response(request_id, -32602, "tool not allowlisted", {"tool": name})
        if name == "safe_sum":
            if not isinstance(arguments, dict):
                return error_response(request_id, -32602, "arguments must be an object")
            if set(arguments) != {"a", "b"}:
                return error_response(request_id, -32602, "safe_sum requires exactly a and b")
            try:
                a = validate_integer(arguments["a"], "a")
                b = validate_integer(arguments["b"], "b")
            except ValueError as exc:
                return error_response(request_id, -32602, str(exc))
            total = a + b
            return result_response(
                request_id,
                {
                    "content": [{"type": "text", "text": str(total)}],
                    "structuredContent": {"sum": total},
                    "isError": False,
                },
            )
    return error_response(request_id, -32601, "Method not found")


class McpHandler(BaseHTTPRequestHandler):
    server_version = "SAREMCPProof/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self.send_error(404)
            return
        header_version = self.headers.get("MCP-Protocol-Version")
        if header_version != PROTOCOL_VERSION:
            response = error_response(None, -32022, "UnsupportedProtocolVersion", {"supported": [PROTOCOL_VERSION]})
            self._write_json(400, response)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(400, error_response(None, -32700, "Parse error"))
            return
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            self._write_json(400, error_response(payload.get("id") if isinstance(payload, dict) else None, -32600, "Invalid Request"))
            return
        method_header = self.headers.get("Mcp-Method")
        if method_header and method_header != payload.get("method"):
            self._write_json(400, error_response(payload.get("id"), -32600, "Mcp-Method header mismatch"))
            return
        response = dispatch(payload)
        self._write_json(200, response)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated MCP 2026-07-28 proof server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("proof server must bind loopback only")
    server = ThreadingHTTPServer((args.host, args.port), McpHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
