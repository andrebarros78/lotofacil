from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "agents" / "mcp_external_authenticated_policy.json"


def load_policy() -> dict[str, Any]:
    with POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


POLICY = load_policy()
PROTOCOL_VERSION = POLICY["protocol_version"]
TOOLS = {tool["name"]: tool for tool in POLICY["allowed_tools"]}
REPOSITORY = POLICY["provider"]["repository_allowlist"][0]
GITHUB_API_ORIGIN = POLICY["provider"]["api_origin"].rstrip("/")
OIDC_AUDIENCE = POLICY["oidc"]["audience"]
OIDC_HOST_SUFFIX = POLICY["oidc"]["allowed_host_suffix"]
EXPECTED_OIDC_ISSUER = "https://token.actions.githubusercontent.com"


class ProviderError(RuntimeError):
    pass


def meta() -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/serverInfo": {
            "name": "sare-authenticated-external-mcp-proof",
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


def _require_empty_arguments(arguments: Any) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    if arguments:
        raise ValueError("tool accepts no arguments")


def _json_https_get(url: str, bearer: str, *, expected_host_suffix: str | None = None) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderError("provider URL must use HTTPS")
    if expected_host_suffix is not None:
        hostname = parsed.hostname.lower()
        suffix = expected_host_suffix.lower()
        if not hostname.endswith(suffix):
            raise ProviderError("provider host is outside the allowlist")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "sare-lotofacil-gap-a06-proof",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise ProviderError(f"provider returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError("authenticated provider request failed") from exc
    if not isinstance(payload, dict):
        raise ProviderError("provider returned non-object JSON")
    return payload


def github_repo_metadata() -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ProviderError("GITHUB_TOKEN is unavailable")
    payload = _json_https_get(f"{GITHUB_API_ORIGIN}/repos/{REPOSITORY}", token)
    if payload.get("full_name") != REPOSITORY:
        raise ProviderError("provider repository identity mismatch")
    return {
        "full_name": payload.get("full_name"),
        "default_branch": payload.get("default_branch"),
        "private": payload.get("private"),
        "archived": payload.get("archived"),
        "visibility": payload.get("visibility"),
    }


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ProviderError("OIDC response is not a JWT")
    encoded = parts[1]
    encoded += "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("OIDC JWT payload is invalid") from exc
    if not isinstance(payload, dict):
        raise ProviderError("OIDC JWT payload is not an object")
    return payload


def github_oidc_identity() -> dict[str, Any]:
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not request_url or not request_token:
        raise ProviderError("GitHub Actions OIDC environment is unavailable")
    parsed = urllib.parse.urlparse(request_url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.lower().endswith(OIDC_HOST_SUFFIX.lower()):
        raise ProviderError("OIDC request endpoint is outside the allowlist")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "audience"]
    query.append(("audience", OIDC_AUDIENCE))
    oidc_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
    response = _json_https_get(oidc_url, request_token, expected_host_suffix=OIDC_HOST_SUFFIX)
    jwt_value = response.get("value")
    if not isinstance(jwt_value, str) or not jwt_value:
        raise ProviderError("OIDC provider did not return a token")
    claims = _decode_jwt_payload(jwt_value)
    audience = claims.get("aud")
    audience_ok = audience == OIDC_AUDIENCE or (isinstance(audience, list) and OIDC_AUDIENCE in audience)
    if claims.get("iss") != EXPECTED_OIDC_ISSUER:
        raise ProviderError("OIDC issuer mismatch")
    if not audience_ok:
        raise ProviderError("OIDC audience mismatch")
    if claims.get("repository") != REPOSITORY:
        raise ProviderError("OIDC repository claim mismatch")
    return {
        "iss": claims.get("iss"),
        "aud": audience,
        "repository": claims.get("repository"),
        "repository_owner": claims.get("repository_owner"),
        "ref": claims.get("ref"),
        "actor": claims.get("actor"),
        "workflow": claims.get("workflow"),
    }


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    request_meta = params.get("_meta") if isinstance(params, dict) else None
    if not isinstance(request_meta, dict):
        return error_response(request_id, -32602, "missing request _meta")
    if request_meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION:
        return error_response(request_id, -32022, "UnsupportedProtocolVersion", {"supported": [PROTOCOL_VERSION]})
    if method in {"initialize", "notifications/initialized"}:
        return error_response(request_id, -32601, "Method not supported by MCP 2026-07-28")
    if method == "server/discover":
        return result_response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "sare-authenticated-external-mcp-proof", "version": "1.0"},
                "capabilities": {"tools": {"list": True, "call": True}},
            },
        )
    if method == "tools/list":
        return result_response(request_id, {"tools": list(TOOLS.values())})
    if method == "tools/call":
        if not isinstance(params, dict):
            return error_response(request_id, -32602, "params must be an object")
        name = params.get("name")
        arguments = params.get("arguments")
        if name not in TOOLS:
            return error_response(request_id, -32602, "tool not allowlisted", {"tool": name})
        try:
            _require_empty_arguments(arguments)
            if name == "github_repo_metadata":
                structured = github_repo_metadata()
            elif name == "github_oidc_identity":
                structured = github_oidc_identity()
            else:
                return error_response(request_id, -32602, "tool not allowlisted")
        except ValueError as exc:
            return error_response(request_id, -32602, str(exc))
        except ProviderError:
            return error_response(request_id, -32050, "AuthenticatedProviderError")
        return result_response(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(structured, sort_keys=True)}],
                "structuredContent": structured,
                "isError": False,
            },
        )
    return error_response(request_id, -32601, "Method not found")


class McpHandler(BaseHTTPRequestHandler):
    server_version = "SAREAuthenticatedMCPProof/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self.send_error(404)
            return
        expected_client_token = os.environ.get("MCP_CLIENT_TOKEN")
        authorization = self.headers.get("Authorization")
        if not expected_client_token or authorization != f"Bearer {expected_client_token}":
            self._write_json(401, error_response(None, -32001, "Unauthorized"))
            return
        header_version = self.headers.get("MCP-Protocol-Version")
        if header_version != PROTOCOL_VERSION:
            self._write_json(400, error_response(None, -32022, "UnsupportedProtocolVersion", {"supported": [PROTOCOL_VERSION]}))
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
        self._write_json(200, dispatch(payload))

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded authenticated external MCP proof server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("proof server must bind loopback only")
    if not os.environ.get("MCP_CLIENT_TOKEN"):
        raise SystemExit("MCP_CLIENT_TOKEN must be supplied at runtime")
    server = ThreadingHTTPServer((args.host, args.port), McpHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
