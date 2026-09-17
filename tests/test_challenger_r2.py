from __future__ import annotations

from dataclasses import replace

import pytest

from sare_lotofacil.experiments.challenger import (
    ChallengerHypothesis,
    ChallengerLeakageError,
    ChampionConfig,
    build_hypothesis_from_episode,
    run_isolated_challenger,
)


def _draws(total: int = 160) -> tuple[tuple[int, ...], ...]:
    draws = []
    for contest in range(1, total + 1):
        start = (contest * 7) % 25
        draw = tuple(sorted(((start + offset) % 25) + 1 for offset in range(15)))
        draws.append(draw)
    return tuple(draws)


def _episode(contest_id: int = 100) -> dict[str, object]:
    return {
        "episode_id": f"post-contest-{contest_id}",
        "contest_id": contest_id,
        "revision": 1,
        "learning_policy": {
            "retrospective_only": True,
            "rewrite_frozen_cards": False,
            "direct_model_tuning_allowed": False,
            "challenger_required": True,
            "promotion_requires_predeclared_validation": True,
        },
    }


def _hypothesis() -> ChallengerHypothesis:
    return build_hypothesis_from_episode(
        _episode(),
        hypothesis_id="hyp-r2-001",
        statement="regularização menor pode responder mais rápido sem usar dados futuros",
        expected_mechanism="reduzir shrinkage mantendo treino prefix-only",
        validation_start_contest=101,
        validation_end_contest=140,
        challenger_lam=50.0,
        delta_min=0.0,
    )


def test_episode_can_only_create_predeclared_future_validation_hypothesis() -> None:
    hypothesis = _hypothesis()
    assert hypothesis.source_contest == 100
    assert hypothesis.validation_start_contest == 101
    assert hypothesis.hypothesis_hash
    assert set(hypothesis.prohibited_selection_data) >= {
        "future_results",
        "validation_targets",
        "prospective_lockbox",
    }


def test_episode_that_allows_direct_tuning_is_rejected() -> None:
    episode = _episode()
    episode["learning_policy"] = dict(episode["learning_policy"], direct_model_tuning_allowed=True)
    with pytest.raises(RuntimeError, match="EPISODE_ALLOWS_DIRECT_MODEL_TUNING"):
        build_hypothesis_from_episode(
            episode,
            hypothesis_id="bad",
            statement="bad",
            expected_mechanism="bad",
            validation_start_contest=101,
            validation_end_contest=140,
            challenger_lam=50.0,
        )


def test_validation_overlap_with_source_contest_is_fail_closed() -> None:
    hypothesis = _hypothesis()
    leaking = replace(hypothesis, validation_start_contest=100)
    with pytest.raises(ChallengerLeakageError, match="VALIDATION_MUST_START_AFTER"):
        leaking.validate()


def test_missing_future_results_blocks_experiment_instead_of_backfilling() -> None:
    hypothesis = replace(_hypothesis(), validation_end_contest=170)
    with pytest.raises(RuntimeError, match="VALIDATION_RESULTS_NOT_AVAILABLE"):
        run_isolated_challenger(_draws(160), hypothesis=hypothesis)


def test_challenger_isolated_from_champion_and_decision_is_predeclared() -> None:
    hypothesis = _hypothesis()
    champion = ChampionConfig()
    before = champion.config_hash
    result = run_isolated_challenger(_draws(), hypothesis=hypothesis, champion=champion)

    assert result.champion_hash_before == before
    assert result.champion_hash_after == before
    assert champion.config_hash == before
    assert result.promotion_applied is False
    assert result.predictive_evidence == "NOT_ESTABLISHED"
    assert result.decision in {"ELIGIBLE_FOR_PROMOTION", "REJECTED"}
    if result.decision == "ELIGIBLE_FOR_PROMOTION":
        assert result.challenger_result.delta_brier_ci_low > hypothesis.delta_min
        assert result.challenger_result.mean_brier < result.champion_result.mean_brier
        assert result.reason == "PREDECLARED_PROMOTION_RULE_SATISFIED"
    else:
        assert result.reason == "PREDECLARED_PROMOTION_RULE_NOT_SATISFIED"
    assert result.content_hash


def test_hypothesis_cannot_relax_stop_or_promotion_rule_after_the_fact() -> None:
    hypothesis = _hypothesis()
    with pytest.raises(ValueError, match="janela fixa"):
        replace(hypothesis, stop_rule="stop_when_good").validate()
    with pytest.raises(ValueError, match="regra de promoção"):
        replace(hypothesis, promotion_rule="promote_if_we_like_it").validate()
