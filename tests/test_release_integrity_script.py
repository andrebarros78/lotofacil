from pathlib import Path

from scripts import prove_release_integrity as proof


def test_primary_card_release_proof_function_executes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(proof, "ARTIFACTS", tmp_path)
    proof.prove_primary_card()
    artifact = tmp_path / "primary_card_release_proof.json"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "PRIMARY_CARD_RELEASE_PROOF_PASS" in text
    assert "M1_TOP15_M2_TIEBREAK_V1" in text
