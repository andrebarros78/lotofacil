from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        rel = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        h.update(len(rel).to_bytes(8, "big"))
        h.update(rel)
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


def prove(*, code_dir: Path, state_dir: Path, before_digest: str, runtime1: Path, runtime2: Path) -> dict[str, object]:
    code_sha = git_head(code_dir)
    state_sha = git_head(state_dir)
    after_digest = tree_digest(state_dir / "operations")
    if before_digest != after_digest:
        raise RuntimeError("F9_OPERATIONAL_STATE_MUTATED_DURING_RECOVERY")
    for marker in (runtime1, runtime2):
        if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != "PASS":
            raise RuntimeError(f"F9_RUNTIME_RECONSTRUCTION_NOT_PROVEN:{marker}")
    return {
        "schema_version": 1,
        "phase": "F9_CLEAN_ROOM_DISASTER_RECOVERY",
        "status": "F9_CLEAN_ROOM_DISASTER_RECOVERY_PROOF_PASS",
        "authority": "GITHUB_ONLY",
        "candidate_code_sha": code_sha,
        "operations_state_sha": state_sha,
        "operational_state_tree_sha256_before": before_digest,
        "operational_state_tree_sha256_after": after_digest,
        "clean_runtime_reconstructions": 2,
        "execution_environment_loss_simulated": True,
        "operational_state_immutable_during_recovery": True,
        "predictive_evidence": "NOT_ESTABLISHED",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--code-dir", required=True)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--before-digest", required=True)
    p.add_argument("--runtime1-marker", required=True)
    p.add_argument("--runtime2-marker", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = prove(
        code_dir=Path(a.code_dir),
        state_dir=Path(a.state_dir),
        before_digest=a.before_digest,
        runtime1=Path(a.runtime1_marker),
        runtime2=Path(a.runtime2_marker),
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
