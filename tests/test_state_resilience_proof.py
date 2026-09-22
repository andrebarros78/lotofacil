from pathlib import Path

from scripts.prove_state_resilience import prove
from sare_lotofacil.operational_state import publish_state_transaction


def test_f8_resilience_harness_survives_restart_replay_and_collision(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    files = {
        "alpha.json": b'{"seed":"alpha"}\n',
        "beta.json": b'{"seed":"beta"}\n',
    }
    for name, content in files.items():
        (source / name).write_bytes(content)
    publish_state_transaction(
        source,
        files,
        generation_id="source-cycle",
        metadata={"source": "github_operational_cycle"},
    )

    result = prove(source, tmp_path / "work", iterations=20)

    assert result["status"] == "F8_CHAOS_RESTART_REPLAY_ENDURANCE_PROOF_PASS"
    assert result["invariants"]["no_hybrid_generation_observed"] is True
    assert result["invariants"]["exact_replay_is_noop"] is True
    assert result["invariants"]["generation_id_collision_is_fail_closed"] is True
    assert result["invariants"]["real_state_is_restart_stable"] is True
    assert result["summary"]["precommit_rollbacks"] > 0
    assert result["summary"]["postcommit_rollforwards"] > 0
    assert result["summary"]["exact_replay_noops"] > 0
    assert result["summary"]["generation_collisions_blocked"] > 0
