from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sare_lotofacil.operational_state import (
    StateTransactionError,
    publish_state_transaction,
    recover_state_transaction,
    verify_state_commit,
)


def _seed_toy_state(path: Path) -> dict[str, bytes]:
    path.mkdir(parents=True, exist_ok=True)
    files = {
        "canonical_history.json": b'{"generation":"old-history"}\n',
        "prospective_ledger.json": b'{"generation":"old-ledger"}\n',
        "latest.json": b'{"generation":"old-latest"}\n',
    }
    for relative, content in files.items():
        (path / relative).write_bytes(content)
    publish_state_transaction(
        path,
        files,
        generation_id="f7-baseline",
        metadata={"source": "github_operational_cycle"},
    )
    return files


def prove(source_state: Path, work_dir: Path) -> dict[str, object]:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    crash_results: list[dict[str, object]] = []
    for crash_after in (1, 2, 3):
        toy = work_dir / f"precommit-{crash_after}"
        old = _seed_toy_state(toy)
        new = {
            "canonical_history.json": b'{"generation":"new-history"}\n',
            "prospective_ledger.json": b'{"generation":"new-ledger"}\n',
            "latest.json": b'{"generation":"new-latest"}\n',
        }
        crashed = False
        try:
            publish_state_transaction(
                toy,
                new,
                generation_id=f"f7-precommit-{crash_after}",
                metadata={"source": "github_operational_cycle"},
                crash_after_replace=crash_after,
            )
        except StateTransactionError as exc:
            crashed = str(exc).startswith("INJECTED_CRASH_AFTER_REPLACE")
        if not crashed:
            raise RuntimeError(f"precommit crash injection did not trigger: {crash_after}")
        recovery = recover_state_transaction(toy)
        if recovery != "PREPARED_ROLLED_BACK":
            raise RuntimeError(f"unexpected precommit recovery: {recovery}")
        if any((toy / relative).read_bytes() != content for relative, content in old.items()):
            raise RuntimeError(f"mixed generation after rollback: {crash_after}")
        verified = verify_state_commit(toy, allow_legacy=False)
        if verified["generation_id"] != "f7-baseline":
            raise RuntimeError("rollback did not preserve previous commit")
        crash_results.append(
            {
                "crash_after_replace": crash_after,
                "recovery": recovery,
                "generation_after_recovery": verified["generation_id"],
            }
        )

    toy = work_dir / "postcommit"
    _seed_toy_state(toy)
    new = {
        "canonical_history.json": b'{"generation":"new-history"}\n',
        "prospective_ledger.json": b'{"generation":"new-ledger"}\n',
        "latest.json": b'{"generation":"new-latest"}\n',
    }
    try:
        publish_state_transaction(
            toy,
            new,
            generation_id="f7-postcommit",
            metadata={"source": "github_operational_cycle"},
            crash_after_commit=True,
        )
    except StateTransactionError as exc:
        if str(exc) != "INJECTED_CRASH_AFTER_COMMIT":
            raise
    else:
        raise RuntimeError("postcommit crash injection did not trigger")
    postcommit_recovery = recover_state_transaction(toy)
    if postcommit_recovery != "COMMITTED_COMPLETED":
        raise RuntimeError(f"unexpected postcommit recovery: {postcommit_recovery}")
    if any((toy / relative).read_bytes() != content for relative, content in new.items()):
        raise RuntimeError("postcommit recovery did not preserve new generation")
    postcommit_verified = verify_state_commit(toy, allow_legacy=False)

    real_state = work_dir / "real-state"
    shutil.copytree(source_state, real_state)
    before = verify_state_commit(real_state, allow_legacy=True)
    latest_bytes = (real_state / "latest.json").read_bytes()
    commit = publish_state_transaction(
        real_state,
        {"latest.json": latest_bytes},
        generation_id="f7-real-state-seal",
        metadata={"source": "f7_proof_seal"},
    )
    after = verify_state_commit(real_state, allow_legacy=False)
    if after["status"] != "STATE_COMMIT_VERIFIED":
        raise RuntimeError("real operational state could not be transactionally sealed")

    (real_state / "latest.json").write_bytes(b'{"tampered":true}\n')
    tamper_blocked = False
    try:
        verify_state_commit(real_state, allow_legacy=False)
    except StateTransactionError:
        tamper_blocked = True
    if not tamper_blocked:
        raise RuntimeError("committed state tampering was not blocked")

    return {
        "status": "F7_CRASH_CONSISTENCY_PROOF_PASS",
        "precommit_crash_matrix": crash_results,
        "postcommit": {
            "recovery": postcommit_recovery,
            "generation_after_recovery": postcommit_verified["generation_id"],
        },
        "real_operational_state": {
            "status_before_seal": before["status"],
            "sealed_generation_id": commit["generation_id"],
            "verified_files": after["verified_files"],
            "tamper_blocked": tamper_blocked,
        },
        "invariants": {
            "precommit_crash_restores_all_old": True,
            "postcommit_crash_preserves_all_new": True,
            "mixed_generation_after_recovery": False,
            "commit_receipt_covers_complete_file_set": True,
            "tamper_detection": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = prove(args.source_state, args.work_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
