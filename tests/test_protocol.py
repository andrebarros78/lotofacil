import pytest

from sare_lotofacil.experiments.protocol import ExperimentProtocol


def protocol(**overrides):
    values = dict(
        hypothesis_id="H-001",
        question="M1 melhora o Brier fora da amostra?",
        h0="Delta Brier <= 0",
        h1="Delta Brier > 0",
        snapshot_id="snap-abc",
    )
    values.update(overrides)
    return ExperimentProtocol(**values)


def test_protocol_hash_is_deterministic_and_sensitive() -> None:
    first = protocol()
    second = protocol()
    assert first.protocol_hash == second.protocol_hash
    assert first.protocol_hash != protocol(delta_min=0.001).protocol_hash


def test_protocol_rejects_noncanonical_baseline() -> None:
    with pytest.raises(ValueError):
        protocol(baseline="frequencia_historica").validate()
