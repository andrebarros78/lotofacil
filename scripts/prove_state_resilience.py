from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sare_lotofacil.operational_state import (
    STATE_COMMIT_FILE,
    StateTransactionError,
    publish_state_transaction,
    recover_state_transaction,
    verify_state_commit,
)

SCHEMA = "f8-chaos-restart-replay-endurance-v1"
WORKER_CRASH = 91
WORKER_EXPECTED_REJECTION = 92


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(state_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(state_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(state_dir).as_posix()
        if relative.startswith(".state-txn/") or relative == ".state_transaction.json":
            continue
        if path.name.startswith(".") and path.name.endswith(".tmp"):
            continue
        hashes[relative] = _sha256(path)
    return hashes


def _write_plan(path: Path, state_dir: Path, generation_id: str, files: dict[str, bytes], metadata: dict[str, object], *, crash_after_replace: int | None = None, crash_after_commit: bool = False) -> None:
    payload = {
        "state_dir": str(state_dir),
        "generation_id": generation_id,
        "files": {name: base64.b64encode(content).decode("ascii") for name, content in sorted(files.items())},
        "metadata": metadata,
        "crash_after_replace": crash_after_replace,
        "crash_after_commit": crash_after_commit,
    }
    path.write_bytes(_canonical(payload))


def _worker_publish(plan_path: Path) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    files = {
        name: base64.b64decode(content.encode("ascii"))
        for name, content in plan["files"].items()
    }
    try:
        result = publish_state_transaction(
            Path(plan["state_dir"]),
            files,
            generation_id=str(plan["generation_id"]),
            metadata=dict(plan["metadata"]),
            crash_after_replace=plan.get("crash_after_replace"),
            crash_after_commit=bool(plan.get("crash_after_commit", False)),
        )
    except StateTransactionError as exc:
        text = str(exc)
        if text.startswith("INJECTED_CRASH_"):
            print(text, flush=True)
            os._exit(WORKER_CRASH)
        print(text, flush=True)
        return WORKER_EXPECTED_REJECTION
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


def _worker_recover(state_dir: Path) -> int:
    outcome = recover_state_transaction(state_dir)
    print(outcome, flush=True)
    return 0


def _worker_verify(state_dir: Path) -> int:
    result = verify_state_commit(state_dir, allow_legacy=False)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


def _run_worker(script: Path, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != expected:
        raise RuntimeError(
            f"worker returncode {proc.returncode} != {expected}; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    return proc


def _synthetic_files(sequence: int) -> dict[str, bytes]:
    return {
        "alpha.json": _canonical({"sequence": sequence, "slot": "alpha"}),
        "beta.json": _canonical({"sequence": sequence, "slot": "beta"}),
        "gamma.json": _canonical({"sequence": sequence, "slot": "gamma"}),
        "delta.json": _canonical({"sequence": sequence, "slot": "delta"}),
    }


def _verify_generation(state_dir: Path, expected_generation: str) -> dict[str, object]:
    verified = verify_state_commit(state_dir, allow_legacy=False)
    if verified["generation_id"] != expected_generation:
        raise RuntimeError(
            f"generation mismatch {verified['generation_id']} != {expected_generation}"
        )
    return verified


def prove(source_state: Path, work_dir: Path, *, iterations: int) -> dict[str, object]:
    if iterations < 20:
        raise ValueError("iterations must be >= 20")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    script = Path(__file__).resolve()

    real_state = work_dir / "real-state"
    shutil.copytree(source_state, real_state)
    real_before = _tree_hashes(real_state)
    real_verified = verify_state_commit(real_state, allow_legacy=False)
    real_restart_rounds = 24
    for _ in range(real_restart_rounds):
        recovered = _run_worker(script, "--worker-recover", str(real_state)).stdout.strip()
        if recovered != "CLEAN":
            raise RuntimeError(f"real state recovery was not CLEAN: {recovered}")
        _run_worker(script, "--worker-verify", str(real_state))
    real_after = _tree_hashes(real_state)
    if real_before != real_after:
        raise RuntimeError("real committed state changed during restart endurance")

    state = work_dir / "synthetic-state"
    state.mkdir()
    base_files = _synthetic_files(0)
    baseline = publish_state_transaction(
        state,
        base_files,
        generation_id="f8-base",
        metadata={"source": "github_operational_cycle", "sequence": 0},
    )
    expected_generation = str(baseline["generation_id"])
    expected_cycle_generation = expected_generation

    events: list[dict[str, object]] = []
    commits = 1
    rollbacks = 0
    rollforwards = 0
    exact_replays = 0
    collisions_blocked = 0
    restarts = real_restart_rounds

    for sequence in range(1, iterations + 1):
        mode = sequence % 5
        generation = f"f8-gen-{sequence:04d}"
        files = _synthetic_files(sequence)
        prior_generation = expected_generation
        source = "github_operational_cycle" if sequence % 4 == 0 else "canonical_prize_update"
        metadata = {"source": source, "sequence": sequence}
        plan = work_dir / f"plan-{sequence:04d}.json"
        event: dict[str, object] = {
            "sequence": sequence,
            "mode": mode,
            "generation": generation,
            "prior_generation": prior_generation,
        }

        if mode == 1:
            crash_at = 1 + (sequence % len(files))
            _write_plan(
                plan,
                state,
                generation,
                files,
                metadata,
                crash_after_replace=crash_at,
            )
            _run_worker(script, "--worker-publish", str(plan), expected=WORKER_CRASH)
            recovery = _run_worker(script, "--worker-recover", str(state)).stdout.strip()
            restarts += 1
            if recovery != "PREPARED_ROLLED_BACK":
                raise RuntimeError(f"unexpected rollback recovery: {recovery}")
            expected_generation = prior_generation
            rollbacks += 1
            event.update({"crash": f"replace-{crash_at}", "recovery": recovery})
        elif mode == 2:
            _write_plan(
                plan,
                state,
                generation,
                files,
                metadata,
                crash_after_commit=True,
            )
            _run_worker(script, "--worker-publish", str(plan), expected=WORKER_CRASH)
            recovery = _run_worker(script, "--worker-recover", str(state)).stdout.strip()
            restarts += 1
            if recovery != "COMMITTED_COMPLETED":
                raise RuntimeError(f"unexpected roll-forward recovery: {recovery}")
            expected_generation = generation
            rollforwards += 1
            commits += 1
            if source == "github_operational_cycle":
                expected_cycle_generation = generation
            event.update({"crash": "after-commit", "recovery": recovery})
        elif mode == 3:
            _write_plan(plan, state, generation, files, metadata)
            _run_worker(script, "--worker-publish", str(plan))
            expected_generation = generation
            commits += 1
            if source == "github_operational_cycle":
                expected_cycle_generation = generation
            before = (state / STATE_COMMIT_FILE).read_bytes()
            _run_worker(script, "--worker-publish", str(plan))
            after = (state / STATE_COMMIT_FILE).read_bytes()
            if before != after:
                raise RuntimeError("exact replay mutated state_commit.json")
            exact_replays += 1
            event.update({"replay": "EXACT_NOOP"})
        elif mode == 4:
            _write_plan(plan, state, generation, files, metadata)
            _run_worker(script, "--worker-publish", str(plan))
            expected_generation = generation
            commits += 1
            if source == "github_operational_cycle":
                expected_cycle_generation = generation

            collision_files = dict(files)
            collision_files["alpha.json"] = _canonical({"sequence": sequence, "slot": "collision"})
            collision_plan = work_dir / f"collision-{sequence:04d}.json"
            _write_plan(collision_plan, state, generation, collision_files, metadata)
            before = _tree_hashes(state)
            _run_worker(
                script,
                "--worker-publish",
                str(collision_plan),
                expected=WORKER_EXPECTED_REJECTION,
            )
            after = _tree_hashes(state)
            if before != after:
                raise RuntimeError("generation collision changed committed state")
            collisions_blocked += 1
            event.update({"collision": "BLOCKED"})
        else:
            _write_plan(plan, state, generation, files, metadata)
            _run_worker(script, "--worker-publish", str(plan))
            expected_generation = generation
            commits += 1
            if source == "github_operational_cycle":
                expected_cycle_generation = generation
            event.update({"publish": "COMMITTED"})

        verified = _verify_generation(state, expected_generation)
        metadata_after = verified.get("metadata", {})
        if expected_generation != "f8-base":
            parent = metadata_after.get("parent_generation_id")
            if parent == expected_generation:
                raise RuntimeError("self-parent generation detected")
        cycle_after = metadata_after.get("cycle_generation_id")
        if cycle_after != expected_cycle_generation:
            raise RuntimeError(
                f"cycle_generation_id drift: {cycle_after} != {expected_cycle_generation}"
            )

        second_recovery = _run_worker(script, "--worker-recover", str(state)).stdout.strip()
        restarts += 1
        if second_recovery != "CLEAN":
            raise RuntimeError(f"second recovery not CLEAN: {second_recovery}")
        _run_worker(script, "--worker-verify", str(state))
        events.append(event)

    final_verified = verify_state_commit(state, allow_legacy=False)
    return {
        "schema": SCHEMA,
        "status": "F8_CHAOS_RESTART_REPLAY_ENDURANCE_PROOF_PASS",
        "iterations": iterations,
        "summary": {
            "committed_generations": commits,
            "precommit_rollbacks": rollbacks,
            "postcommit_rollforwards": rollforwards,
            "exact_replay_noops": exact_replays,
            "generation_collisions_blocked": collisions_blocked,
            "process_restart_recoveries": restarts,
            "real_state_restart_rounds": real_restart_rounds,
        },
        "real_operational_state": {
            "generation_id": real_verified["generation_id"],
            "verified_files": real_verified["verified_files"],
            "byte_stable_across_restarts": real_before == real_after,
        },
        "final_synthetic_state": {
            "generation_id": final_verified["generation_id"],
            "verified_files": final_verified["verified_files"],
            "cycle_generation_id": final_verified["metadata"].get("cycle_generation_id"),
        },
        "invariants": {
            "no_hybrid_generation_observed": True,
            "precommit_crash_rolls_back": True,
            "postcommit_crash_rolls_forward": True,
            "recovery_is_restart_idempotent": True,
            "exact_replay_is_noop": True,
            "generation_id_collision_is_fail_closed": True,
            "no_self_parent_generation": True,
            "cycle_generation_id_preserved_across_auxiliary_generations": True,
            "real_state_is_restart_stable": True,
        },
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-state", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--worker-publish", type=Path)
    parser.add_argument("--worker-recover", type=Path)
    parser.add_argument("--worker-verify", type=Path)
    args = parser.parse_args()

    if args.worker_publish is not None:
        return _worker_publish(args.worker_publish)
    if args.worker_recover is not None:
        return _worker_recover(args.worker_recover)
    if args.worker_verify is not None:
        return _worker_verify(args.worker_verify)

    if args.source_state is None or args.work_dir is None or args.out is None:
        parser.error("--source-state, --work-dir and --out are required")

    result = prove(args.source_state, args.work_dir, iterations=args.iterations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(_canonical(result))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
