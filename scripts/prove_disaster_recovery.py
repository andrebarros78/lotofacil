from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

REQUIRED_GATES = (
    "CI",
    "Scientific Gate",
    "Operational Integrity Gate",
    "Security/Sanitization Gate",
    "Release Candidate Gate",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def parse_sha256sums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in path.read_text(encoding="ascii").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise RuntimeError("DR_INVALID_SHA256SUMS_LINE")
        digest, name = parts
        name = name.strip()
        if "/" in name or "\\" in name or name in {".", ".."}:
            raise RuntimeError("DR_UNSAFE_SHA256SUMS_NAME")
        if name in entries:
            raise RuntimeError("DR_DUPLICATE_SHA256SUMS_NAME")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise RuntimeError("DR_INVALID_SHA256SUM")
        entries[name] = digest.lower()
    if not entries:
        raise RuntimeError("DR_EMPTY_SHA256SUMS")
    return entries


def verify_checksums(release_dir: Path, sums: dict[str, str]) -> list[dict[str, object]]:
    verified: list[dict[str, object]] = []
    for name, expected in sorted(sums.items()):
        target = release_dir / name
        if not target.is_file():
            raise RuntimeError(f"DR_RELEASE_ASSET_MISSING:{name}")
        actual = _sha256(target)
        if actual != expected:
            raise RuntimeError(f"DR_RELEASE_ASSET_HASH_MISMATCH:{name}")
        verified.append({"name": name, "sha256": actual, "bytes": target.stat().st_size})
    return verified


def validate_manifest(
    manifest: dict[str, object],
    *,
    code_sha: str,
    state_sha: str,
    expected_release_sha: str | None,
) -> None:
    if manifest.get("schema_version") != "r4-release-manifest-v1":
        raise RuntimeError("DR_RELEASE_MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("canonical_sha") != code_sha:
        raise RuntimeError("DR_RELEASE_CODE_SHA_MISMATCH")
    if expected_release_sha and code_sha != expected_release_sha:
        raise RuntimeError("DR_EXPECTED_RELEASE_SHA_MISMATCH")
    if manifest.get("operations_state_sha") != state_sha:
        raise RuntimeError("DR_OPERATIONAL_STATE_SHA_MISMATCH")
    gates = manifest.get("gate_results")
    if not isinstance(gates, dict):
        raise RuntimeError("DR_GATE_RESULTS_MISSING")
    for gate in REQUIRED_GATES:
        if gates.get(gate) != "success":
            raise RuntimeError(f"DR_REQUIRED_GATE_NOT_SUCCESS:{gate}")
    if manifest.get("release_proof") != "success":
        raise RuntimeError("DR_RELEASE_PROOF_NOT_SUCCESS")
    if manifest.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("DR_PREDICTIVE_EVIDENCE_CLASSIFICATION_MISMATCH")


def prove(
    *,
    release_dir: Path,
    code_dir: Path,
    state_dir: Path,
    expected_release_sha: str | None,
    started_at_epoch: float,
    recreated_runtime: bool,
) -> dict[str, object]:
    manifest_path = release_dir / "release-manifest-v1.1.10.json"
    sums_path = release_dir / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        raise RuntimeError("DR_RELEASE_MANIFEST_OR_SUMS_MISSING")

    sums = parse_sha256sums(sums_path)
    verified_assets = verify_checksums(release_dir, sums)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    code_sha = _git_head(code_dir)
    state_sha = _git_head(state_dir)
    validate_manifest(
        manifest,
        code_sha=code_sha,
        state_sha=state_sha,
        expected_release_sha=expected_release_sha,
    )
    if not recreated_runtime:
        raise RuntimeError("DR_RUNTIME_RECREATION_NOT_PROVEN")

    elapsed = max(0.0, time.time() - started_at_epoch)
    return {
        "status": "GITHUB_ONLY_DR_PROOF_PASS",
        "release_version": manifest["version"],
        "release_tag": manifest["tag"],
        "release_sha": code_sha,
        "operations_state_sha": state_sha,
        "release_manifest_sha256": _sha256(manifest_path),
        "verified_release_assets": verified_assets,
        "rpo_observed": {
            "code_commits": 0,
            "operational_state_commits": 0,
            "scope": "committed canonical Git states recovered by exact SHA",
        },
        "rto_observed_seconds": round(elapsed, 3),
        "execution_environment_recreated": True,
        "authority": "GITHUB_ONLY",
        "external_dependencies": [
            "GitHub repository and Git refs",
            "GitHub Releases/Actions artifact hosting",
            "GitHub-hosted ubuntu-latest runner",
            "Python package index access for locked third-party dependencies",
        ],
        "not_automatically_recoverable": [
            "GitHub service availability itself",
            "account/OAuth credentials and organization ownership outside Git history",
            "native repository ruleset metadata if GitHub repository metadata is lost",
        ],
        "manual_steps_inevitable": [
            "restore or re-authorize GitHub account access if credentials are lost",
            "recreate native rulesets from documented policy if repository metadata is lost",
        ],
        "predictive_evidence": manifest["predictive_evidence"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--code-dir", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--expected-release-sha")
    parser.add_argument("--started-at-epoch", type=float, required=True)
    parser.add_argument("--recreated-runtime", action="store_true")
    parser.add_argument("--out", default="artifacts/disaster_recovery_proof.json")
    args = parser.parse_args()

    result = prove(
        release_dir=Path(args.release_dir),
        code_dir=Path(args.code_dir),
        state_dir=Path(args.state_dir),
        expected_release_sha=args.expected_release_sha,
        started_at_epoch=args.started_at_epoch,
        recreated_runtime=args.recreated_runtime,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
