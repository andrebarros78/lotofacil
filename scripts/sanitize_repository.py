from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_MAX_TEXT_BYTES = 2_000_000

FORBIDDEN_PATH_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "build",
    "dist",
    "artifacts",
}

FORBIDDEN_BASENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
    "service_account.json",
    ".DS_Store",
    "Thumbs.db",
    ".coverage",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".bak",
    ".tmp",
    ".swp",
    ".pyc",
    ".pyo",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".zip",
    ".7z",
    ".tgz",
    ".gz",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY_MATERIAL",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "GITHUB_TOKEN",
        re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "GITHUB_FINE_GRAINED_TOKEN",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "AWS_ACCESS_KEY",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "OPENAI_API_KEY",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "SLACK_TOKEN",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    (
        "GOOGLE_API_KEY",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ),
    (
        "BASIC_AUTH_URL",
        re.compile(r"https?://[^/\s:@]+:[^/\s@]+@"),
    ),
)

GENERIC_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\b"
    r"\s*[:=]\s*[\"']([^\"'\r\n]{8,})[\"']"
)

ACTION_USE_PATTERN = re.compile(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)")
PINNED_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
REMOTE_PIPE_EXECUTION_PATTERN = re.compile(
    r"(?im)\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:sh|bash)\b"
)

PLACEHOLDER_MARKERS = {
    "${{",
    "secrets.",
    "os.environ",
    "getenv",
    "placeholder",
    "example",
    "dummy",
    "fake",
    "redacted",
    "changeme",
    "not-a-secret",
    "not_a_secret",
    "test-only",
    "test_only",
}


def _git_tracked_files(root: Path) -> list[Path] | None:
    """Return tracked files only when root is the Git worktree root.

    Git ls-files resolves paths relative to the repository top-level even when
    invoked from a nested directory. Treating those paths as relative to an
    arbitrary nested scan root can silently produce an empty scan. For
    non-root directories we intentionally fall back to recursive discovery
    scoped to the requested directory.
    """

    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    try:
        git_root = Path(top_level).resolve()
    except (OSError, RuntimeError):
        return None

    if git_root != root.resolve():
        return None

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    entries = [entry for entry in completed.stdout.split(b"\0") if entry]
    return [root / entry.decode("utf-8", errors="strict") for entry in entries]


def discover_files(root: Path) -> list[Path]:
    root = root.resolve()
    tracked = _git_tracked_files(root)
    if tracked is not None:
        return sorted(path for path in tracked if path.is_file())

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def _forbidden_path_reason(relative: Path) -> str | None:
    parts = relative.parts
    if any(part in FORBIDDEN_PATH_PARTS or part.endswith(".egg-info") for part in parts):
        return "GENERATED_OR_RUNTIME_PATH"

    name = relative.name
    if name in FORBIDDEN_BASENAMES or name.startswith(".env."):
        return "SENSITIVE_OR_RUNTIME_FILE"

    lower_name = name.lower()
    if any(lower_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
        return "GENERATED_BINARY_OR_SECRET_FILE"

    return None


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return any(marker in normalized for marker in PLACEHOLDER_MARKERS)


def _scan_workflow_supply_chain(relative: str, text: str) -> list[dict[str, Any]]:
    if not relative.startswith(".github/workflows/") or not relative.endswith((".yml", ".yaml")):
        return []

    violations: list[dict[str, Any]] = []
    for match in ACTION_USE_PATTERN.finditer(text):
        action_spec = match.group(1)
        if action_spec.startswith("./") or action_spec.startswith("docker://"):
            continue
        if "@" not in action_spec:
            violations.append(
                {
                    "code": "UNPINNED_GITHUB_ACTION",
                    "path": relative,
                    "line": _line_number(text, match.start()),
                    "action": action_spec,
                }
            )
            continue
        _, ref = action_spec.rsplit("@", 1)
        if not PINNED_SHA_PATTERN.fullmatch(ref):
            violations.append(
                {
                    "code": "UNPINNED_GITHUB_ACTION",
                    "path": relative,
                    "line": _line_number(text, match.start()),
                    "action": action_spec,
                }
            )

    for match in REMOTE_PIPE_EXECUTION_PATTERN.finditer(text):
        violations.append(
            {
                "code": "REMOTE_PIPE_EXECUTION",
                "path": relative,
                "line": _line_number(text, match.start()),
            }
        )

    return violations


def _scan_text(relative: str, text: str) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []

    for code, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            violations.append(
                {
                    "code": code,
                    "path": relative,
                    "line": _line_number(text, match.start()),
                }
            )

    for match in GENERIC_CREDENTIAL_ASSIGNMENT.finditer(text):
        value = match.group(2)
        if _looks_like_placeholder(value):
            continue
        violations.append(
            {
                "code": "HARDCODED_CREDENTIAL_ASSIGNMENT",
                "path": relative,
                "line": _line_number(text, match.start()),
                "credential_kind": match.group(1).lower(),
            }
        )

    violations.extend(_scan_workflow_supply_chain(relative, text))
    return violations


def scan_repository(root: Path, *, max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES) -> dict[str, Any]:
    root = root.resolve()
    files = discover_files(root)

    violations: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    text_files_scanned = 0
    binary_or_large_files_skipped = 0
    total_bytes = 0

    for path in files:
        relative_path = path.relative_to(root)
        relative = relative_path.as_posix()
        data = path.read_bytes()
        total_bytes += len(data)
        digest = hashlib.sha256(data).hexdigest()
        manifest.append({"path": relative, "sha256": digest, "bytes": len(data)})

        reason = _forbidden_path_reason(relative_path)
        if reason is not None:
            violations.append({"code": reason, "path": relative})

        if len(data) > max_text_bytes or b"\x00" in data:
            binary_or_large_files_skipped += 1
            continue

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            binary_or_large_files_skipped += 1
            continue

        text_files_scanned += 1
        violations.extend(_scan_text(relative, text))

    manifest_digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    status = "REPOSITORY_SANITIZATION_PASS" if not violations else "REPOSITORY_SANITIZATION_FAIL"
    return {
        "schema_version": 1,
        "status": status,
        "policy": {
            "tracked_files_preferred": True,
            "generated_runtime_paths_forbidden": True,
            "credential_material_forbidden": True,
            "private_key_material_forbidden": True,
            "runtime_databases_forbidden": True,
            "generated_archives_forbidden": True,
            "external_actions_sha_pinned": True,
            "remote_pipe_execution_forbidden": True,
            "canonical_state_mutation": False,
        },
        "metrics": {
            "files_scanned": len(files),
            "text_files_scanned": text_files_scanned,
            "binary_or_large_files_skipped": binary_or_large_files_skipped,
            "total_bytes": total_bytes,
            "violations": len(violations),
        },
        "manifest_sha256": manifest_digest,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize and audit the SARE Lotofácil repository checkout.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--max-text-bytes", type=int, default=DEFAULT_MAX_TEXT_BYTES)
    args = parser.parse_args()

    report = scan_repository(args.root, max_text_bytes=args.max_text_bytes)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Never emit the detailed scan report to stdout. The report is derived
    # from files that may contain secrets; even though violation records are
    # designed to contain metadata only, keeping stdout to a constant status
    # string prevents accidental clear-text secret propagation in CI logs.
    passed = report["status"] == "REPOSITORY_SANITIZATION_PASS"
    print("REPOSITORY_SANITIZATION_PASS" if passed else "REPOSITORY_SANITIZATION_FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
