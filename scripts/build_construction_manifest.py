from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stable-gate-run-id", required=True)
    parser.add_argument("--release-proof-run-id", required=True)
    parser.add_argument("--dr-run-id", required=True)
    parser.add_argument("--out", default="artifacts/construction_manifest.json")
    args = parser.parse_args()

    artifacts = [
        Path("artifacts/third_party_history_report.json"),
        Path("artifacts/r6_integrated_chain.json"),
        Path("artifacts/r6_repository_sanitization.json"),
        Path("artifacts/r6_release_recovery.json"),
    ]
    for item in artifacts:
        if not item.is_file():
            raise RuntimeError(f"R6_REQUIRED_ARTIFACT_MISSING:{item}")

    evidence_paths = [
        Path("docs/evidence/R0_BASELINE_RECONCILED_2026-09-17.md"),
        Path("docs/evidence/R1_FREEZE_INTEGRITY_PROVEN_2026-09-17.md"),
        Path("docs/evidence/R2_POST_CONTEST_CHALLENGER_PROVEN_2026-09-17.md"),
        Path("docs/evidence/R3_MERGE_GATES_PROVEN_2026-09-17.md"),
        Path("docs/evidence/R4_FORMAL_RELEASE_PROVEN_2026-09-17.md"),
        Path("docs/evidence/R5_GITHUB_ONLY_DISASTER_RECOVERY_PROVEN_2026-09-17.md"),
    ]
    for item in evidence_paths:
        if not item.is_file() or "status: PROVEN" not in item.read_text(encoding="utf-8"):
            raise RuntimeError(f"R6_STAGE_EVIDENCE_NOT_PROVEN:{item}")

    manifest: dict[str, object] = {
        "schema_version": "construction-manifest-v1",
        "construction_id": "SARE-LOTOFACIL-CONSTRUCTION-PROVEN-1.1.10",
        "version": "1.1.10",
        "canonical_construction_sha": os.environ["GITHUB_SHA"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "gates": [
            {"name": "R6 stable merge gates", "run_id": int(args.stable_gate_run_id)},
            {"name": "R4 release proof", "run_id": int(args.release_proof_run_id)},
            {"name": "R5 disaster recovery", "run_id": int(args.dr_run_id)},
            {"name": "R6 integrated construction", "run_id": int(os.environ["GITHUB_RUN_ID"])},
        ],
        "artifact_hashes": {str(path): sha256(path) for path in artifacts},
        "stage_evidence_hashes": {str(path): sha256(path) for path in evidence_paths},
        "test_inventory": [
            "full pytest suite under locked Python 3.13 environment",
            "real-history third-party/CAIXA checkpoint verification",
            "scientific gate tests for baseline, backtest integrity and Challenger",
            "controlled integrated generation/freeze/recovery/post-contest/RAG/Challenger chain",
            "idempotent replay and restart recovery",
            "release/state reconstruction verification",
            "repository sanitization",
            "governance + agent ecosystem + doctor",
        ],
        "stages": {f"R{i}": "PROVEN" for i in range(7)},
        "known_exceptions": [
            "predictive advantage remains NOT_ESTABLISHED",
            "R6 operational contest fixture is controlled integration evidence, not a historical prospective claim",
            "GitHub availability and account credential recovery remain external dependencies documented by R5",
        ],
        "claims_allowed": [
            "the construction pipeline R0-R6 is implemented and reproducibly proven",
            "freeze immutability, controlled learning, protected merge gates, formal release and GitHub-only DR are proven engineering properties",
            "RPO observed for committed canonical Git states in R5 was zero commits",
        ],
        "claims_prohibited": [
            "proven predictive advantage over chance",
            "historical prospective status for controlled integration fixtures",
            "automatic Champion promotion from RAG or retrospective episodes",
            "lockbox retuning using observed targets",
            "guaranteed availability independent of GitHub and external package infrastructure",
        ],
        "p0_open_blockers": [],
        "predictive_evidence": "NOT_ESTABLISHED",
    }
    manifest["manifest_hash_algorithm"] = "sha256(canonical-json-without-manifest_hash)"
    manifest["manifest_hash"] = canonical_hash(manifest)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    check = json.loads(out.read_text(encoding="utf-8"))
    stated = check.pop("manifest_hash")
    if canonical_hash(check) != stated:
        raise RuntimeError("R6_MANIFEST_SELF_HASH_MISMATCH")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
