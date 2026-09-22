from __future__ import annotations

from pathlib import Path

import pytest

from scripts.prove_f9_clean_room_recovery import prove, tree_digest


def _git_init(path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "f9@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "F9 Proof"], check=True)
    (path / "tracked.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def test_tree_digest_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "operations"
    root.mkdir()
    (root / "b").write_text("2", encoding="utf-8")
    (root / "a").write_text("1", encoding="utf-8")
    assert tree_digest(root) == tree_digest(root)


def test_proof_fails_closed_if_state_changes(tmp_path: Path) -> None:
    code = tmp_path / "code"
    state = tmp_path / "state"
    code.mkdir()
    state.mkdir()
    _git_init(code)
    _git_init(state)
    operations = state / "operations"
    operations.mkdir()
    (operations / "state.json").write_text("before", encoding="utf-8")
    before = tree_digest(operations)
    (operations / "state.json").write_text("after", encoding="utf-8")
    m1 = tmp_path / "r1"
    m2 = tmp_path / "r2"
    m1.write_text("PASS\n", encoding="utf-8")
    m2.write_text("PASS\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="F9_OPERATIONAL_STATE_MUTATED"):
        prove(code_dir=code, state_dir=state, before_digest=before, runtime1=m1, runtime2=m2)


def test_proof_requires_both_clean_runtime_markers(tmp_path: Path) -> None:
    code = tmp_path / "code"
    state = tmp_path / "state"
    code.mkdir()
    state.mkdir()
    _git_init(code)
    _git_init(state)
    operations = state / "operations"
    operations.mkdir()
    (operations / "state.json").write_text("stable", encoding="utf-8")
    before = tree_digest(operations)
    m1 = tmp_path / "r1"
    m2 = tmp_path / "r2"
    m1.write_text("PASS\n", encoding="utf-8")
    m2.write_text("FAIL\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="F9_RUNTIME_RECONSTRUCTION_NOT_PROVEN"):
        prove(code_dir=code, state_dir=state, before_digest=before, runtime1=m1, runtime2=m2)
