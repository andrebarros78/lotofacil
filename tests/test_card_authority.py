from __future__ import annotations

import pytest

from sare_lotofacil.portfolios.authority import (
    AUTHORITY_ID,
    POLICY_OPERATOR,
    POLICY_PRIMARY,
    POLICY_UNIFORM,
    STATUS_FROZEN,
    STATUS_PREVIEW,
    CardGenerationService,
    operator_card_for_generation_index,
    validate_card_artifact,
)
from sare_lotofacil.portfolios.frozen import card_for_generation_index


def test_preview_is_explicitly_non_operational() -> None:
    artifact = CardGenerationService.preview_uniform(
        card_count=3,
        seed=77,
        target_contest=100,
        data_snapshot_hash="data-hash",
        storage_snapshot_id="snap-1",
        storage_snapshot_hash="storage-hash",
    )

    assert artifact.authority_id == AUTHORITY_ID
    assert artifact.policy_id == POLICY_UNIFORM
    assert artifact.status == STATUS_PREVIEW
    assert artifact.operational_use_allowed is False
    with pytest.raises(RuntimeError, match="CARD_ARTIFACT_NOT_OPERATIONAL"):
        validate_card_artifact(artifact.to_dict(), require_operational=True)


def test_persistable_uniform_artifact_is_frozen_and_hash_verified() -> None:
    artifact = CardGenerationService.freeze_uniform(
        card_count=3,
        seed=77,
        target_contest=100,
        data_snapshot_hash="data-hash",
        storage_snapshot_id="snap-1",
        storage_snapshot_hash="storage-hash",
    )

    validated = validate_card_artifact(
        artifact.to_dict(),
        expected_status=STATUS_FROZEN,
        expected_cards=artifact.cards,
        require_operational=True,
    )

    assert validated.policy_id == POLICY_UNIFORM
    assert validated.artifact_sha256 == artifact.artifact_sha256


def test_artifact_rejects_coherently_tampered_card_without_rehash() -> None:
    artifact = CardGenerationService.freeze_uniform(
        card_count=1,
        seed=12,
        target_contest=100,
    )
    payload = artifact.to_dict()
    payload["cards"][0] = list(range(11, 26))

    with pytest.raises(RuntimeError, match="CARD_ARTIFACT_HASH_OR_PAYLOAD_MISMATCH"):
        validate_card_artifact(payload)


def test_primary_and_operator_policies_share_same_authority_contract() -> None:
    primary = CardGenerationService.freeze_primary(
        card=range(1, 16),
        target_contest=101,
        training_last_contest=100,
        decision_sha256="decision",
        primary_model="M1",
        secondary_model="M2",
        selection_method="method",
        data_snapshot_hash="data",
        storage_snapshot_id="snap",
        storage_snapshot_hash="storage",
    )
    operator = CardGenerationService.freeze_operator_batch(
        cards=(range(11, 26),),
        target_contest=101,
        data_snapshot_hash="data",
        storage_snapshot_id="snap",
        storage_snapshot_hash="storage",
        request_fingerprint="request",
    )

    assert primary.authority_id == operator.authority_id == AUTHORITY_ID
    assert primary.policy_id == POLICY_PRIMARY
    assert operator.policy_id == POLICY_OPERATOR
    assert primary.status == operator.status == STATUS_FROZEN


def test_operator_generation_sequence_is_preserved_by_authority_refactor() -> None:
    for index in (0, 1, 2, 17, 999):
        assert card_for_generation_index(3785, index) == operator_card_for_generation_index(3785, index)
