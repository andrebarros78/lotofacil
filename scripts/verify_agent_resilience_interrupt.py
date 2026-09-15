from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_agent_resilience_proof import (  # noqa: E402
    artifact_path,
    checkpoint_hash,
    definition_fingerprint,
    load_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify expected resilience interruption evidence.")
    parser.add_argument("--checkpoint", default="artifacts/agent_resilience_checkpoint.json")
    parser.add_argument("--report", default="artifacts/agent_resilience_interrupted.json")
    parser.add_argument("--expected-completed", type=int, default=3)
    args = parser.parse_args()

    checkpoint_path = artifact_path(args.checkpoint)
    report_path = artifact_path(args.report)
    report = load_json(report_path)
    checkpoint = load_json(checkpoint_path)

    if report.get("status") != "AGENT_RESILIENCE_EXPECTED_INTERRUPTION":
        raise SystemExit("interruption report status mismatch")
    if report.get("completed_before_interruption") != args.expected_completed:
        raise SystemExit("unexpected completed mission count before interruption")
    if checkpoint.get("next_index") != args.expected_completed:
        raise SystemExit("checkpoint next_index mismatch")
    if checkpoint.get("definition_fingerprint_sha256") != definition_fingerprint():
        raise SystemExit("checkpoint definition fingerprint mismatch")
    if checkpoint.get("checkpoint_payload_sha256") != checkpoint_hash(checkpoint):
        raise SystemExit("checkpoint payload hash mismatch")
    if checkpoint.get("injected_interruptions") != 1:
        raise SystemExit("controlled interruption was not recorded")

    print(json.dumps({
        "status": "EXPECTED_INTERRUPTION_VERIFIED",
        "completed": args.expected_completed,
        "checkpoint_payload_sha256": checkpoint["checkpoint_payload_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
