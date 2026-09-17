from pathlib import Path

from scripts.prove_integrated_construction_r6 import run


def test_r6_controlled_integrated_chain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "r6-test-sha")
    monkeypatch.setenv("GITHUB_RUN_ID", "r6-test-run")
    proof = run(tmp_path)
    assert proof["status"] == "R6_INTEGRATED_CHAIN_PASS"
    assert proof["classification"] == "CONTROLLED_INTEGRATION_FIXTURE_NOT_HISTORICAL_PROSPECTIVE"
    assert proof["operational_fixture"]["immutable"] is True
    assert proof["operational_fixture"]["episode_count"] == 1
    assert proof["operational_fixture"]["rag_read_only_recovered"] is True
    assert proof["challenger"]["promotion_applied"] is False
    assert proof["challenger"]["predictive_evidence"] == "NOT_ESTABLISHED"
    assert proof["operator_registry"]["replay_generated"] == 0
