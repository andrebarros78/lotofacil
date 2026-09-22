from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def prove(repo: Path, f9_marker: Path) -> dict[str, object]:
    readme = (repo / "README.md").read_text(encoding="utf-8")
    hardening = json.loads((repo / "governance/terminal-hardening.json").read_text(encoding="utf-8"))
    mission = (repo / "docs/MISSION_PROVEN_1_1_10.md").read_text(encoding="utf-8")
    marker = json.loads(f9_marker.read_text(encoding="utf-8"))
    if marker.get("status") != "F9_CLEAN_ROOM_DISASTER_RECOVERY_PROOF_PASS":
        raise RuntimeError("F10_REQUIRES_F9_PROVEN")
    if marker.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("F10_SCIENTIFIC_STATE_REGRESSION")
    if hardening.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("F10_HARDENING_SCIENTIFIC_STATE_REGRESSION")
    if "Não há vantagem preditiva comprovada." not in readme:
        raise RuntimeError("F10_PUBLIC_SCIENTIFIC_DISCLAIMER_MISSING")
    if "GitHub-only" not in readme or "GitHub-only" not in mission:
        raise RuntimeError("F10_GITHUB_ONLY_AUTHORITY_MISSING")
    if not re.fullmatch(r"[0-9a-f]{40}", head(repo)):
        raise RuntimeError("F10_INVALID_CODE_IDENTITY")
    return {
        "schema_version": 1,
        "phase": "F10_TERMINAL_MISSION_PROOF",
        "status": "F10_TERMINAL_MISSION_PROOF_PASS",
        "candidate_code_sha": head(repo),
        "f9_status": marker["status"],
        "github_only_authority": True,
        "terminal_hardening_active": True,
        "public_scientific_disclaimer": True,
        "predictive_evidence": "NOT_ESTABLISHED",
        "mission_state": "MISSION_PROVEN",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--f9-proof", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = prove(Path(a.repo), Path(a.f9_proof))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
