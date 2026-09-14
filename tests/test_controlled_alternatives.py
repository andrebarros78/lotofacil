from __future__ import annotations

from sare_lotofacil.simulation.validation import (
    assess_temporal_memory_separation,
    measure_marginal_bias_power,
)


def test_t17_controlled_marginal_bias_has_measured_power() -> None:
    result = measure_marginal_bias_power(
        replications=30,
        draw_count=400,
        target_number=16,
        target_probability=0.72,
        alpha=0.05,
        base_seed=20260914,
    )

    assert result.detections >= 24
    assert result.power >= 0.80
    assert result.mean_target_effect >= 0.08


def test_t18_temporal_memory_is_detected_without_marginal_confusion() -> None:
    result = assess_temporal_memory_separation(
        draw_count=600,
        memory_probability=0.30,
        retained_count=12,
        alpha=0.05,
        seed=20260914,
        permutation_replications=399,
    )

    # "Sem confusão marginal" é definido pela família inferencial canônica:
    # nenhuma rejeição marginal após correção de Holm. O efeito marginal máximo
    # permanece no resultado como diagnóstico descritivo, sem limiar ad hoc.
    assert result.marginal_alerts == 0
    assert result.temporal_alerts >= 1
    assert result.lag1_effect > 0.50
    assert result.lag1_p_holm < 0.05
