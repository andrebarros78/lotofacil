from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from sare_lotofacil.persistence.backup import database_integrity
from sare_lotofacil.persistence.db import connect
from sare_lotofacil.persistence.evidence import verify_source_artifacts
from sare_lotofacil.persistence.operations import list_snapshots
from sare_lotofacil.persistence.repository import load_snapshot_draws
from sare_lotofacil.statistics.inference import (
    fixed_split_frequency_shift,
    marginal_tests,
    pair_tests,
    temporal_lag_permutation_tests,
)

RIS_SCHEMA_VERSION = "ris-categorical-v1"
DEFAULT_ALPHA = 0.05
DEFAULT_TEMPORAL_LAGS = (1, 2, 3, 5, 10)
DEFAULT_TEMPORAL_REPLICATIONS = 999
DEFAULT_TEMPORAL_SEED = 20260911


def _strongest(stats) -> dict[str, Any] | None:
    if not stats:
        return None
    item = min(stats, key=lambda value: (value.p_holm, -abs(value.effect), value.label))
    return {
        "label": item.label,
        "observed": item.observed,
        "expected": item.expected,
        "effect": item.effect,
        "p_value": item.p_value,
        "p_holm": item.p_holm,
    }


def _predictive_state(path: str | Path) -> tuple[str, dict[str, Any]]:
    with connect(path) as connection:
        promotions = int(connection.execute("SELECT COUNT(*) FROM model_promotions").fetchone()[0])
        experiments = int(connection.execute("SELECT COUNT(*) FROM experiment_runs").fetchone()[0])
    if promotions:
        return "REPLICATED", {
            "replicated_promotions": promotions,
            "registered_experiments": experiments,
            "source": "model_promotions",
        }
    return "NOT_ESTABLISHED", {
        "replicated_promotions": 0,
        "registered_experiments": experiments,
        "source": "model_promotions",
        "note": "Experimentos retrospectivos não equivalem a evidência prospectiva replicada.",
    }


def build_categorical_ris_from_draws(
    draws: Sequence[Iterable[int]],
    *,
    snapshot_id: str | None,
    data_state: str,
    data_evidence: dict[str, Any],
    predictive_state: str,
    predictive_evidence: dict[str, Any],
    alpha: float = DEFAULT_ALPHA,
    temporal_lags: tuple[int, ...] = DEFAULT_TEMPORAL_LAGS,
    temporal_replications: int = DEFAULT_TEMPORAL_REPLICATIONS,
    temporal_seed: int = DEFAULT_TEMPORAL_SEED,
) -> dict[str, Any]:
    """Calcula o painel RIS categórico a partir dos mesmos motores analíticos do SARE."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha deve estar entre 0 e 1")
    if temporal_replications <= 0:
        raise ValueError("temporal_replications deve ser positivo")
    if data_state not in {"VERIFIED", "LIMITED", "INVALID"}:
        raise ValueError("data_state inválido")
    if predictive_state not in {"NOT_ESTABLISHED", "UNDER_TEST", "REPLICATED"}:
        raise ValueError("predictive_state inválido")

    normalized_draws = tuple(tuple(draw) for draw in draws)
    dimensions: dict[str, dict[str, Any]] = {
        "data_integrity": {
            "state": data_state,
            "evidence": data_evidence,
        }
    }

    if not normalized_draws:
        reason = "Nenhum snapshot publicado está disponível para análise categórica."
        for key in ("uniformity", "cooccurrence", "temporal", "regime"):
            dimensions[key] = {"state": "INCONCLUSIVE", "evidence": {"reason": reason}}
        dimensions["predictive_evidence"] = {
            "state": predictive_state,
            "evidence": predictive_evidence,
        }
        return {
            "schema_version": RIS_SCHEMA_VERSION,
            "numeric_ris_enabled": False,
            "score": None,
            "snapshot_id": snapshot_id,
            "contest_count": 0,
            "alpha": alpha,
            "dimensions": dimensions,
            "guardrails": [
                "RIS_NUMERIC_FORBIDDEN_IN_1_X",
                "COMPATIBLE_IS_NOT_PROOF_OF_RANDOMNESS",
                "NO_PREDICTIVE_ADVANTAGE_FROM_CATEGORICAL_STATUS",
            ],
        }

    marginal = marginal_tests(normalized_draws)
    marginal_alerts = [item for item in marginal if item.p_holm < alpha]
    dimensions["uniformity"] = {
        "state": "ALERT" if marginal_alerts else "COMPATIBLE",
        "evidence": {
            "method": "exact_binomial_two_sided",
            "family_size": len(marginal),
            "correction": "holm",
            "alpha": alpha,
            "alerts": len(marginal_alerts),
            "min_adjusted_p": min(item.p_holm for item in marginal),
            "max_abs_effect": max(abs(item.effect) for item in marginal),
            "strongest": _strongest(marginal),
            "interpretation": "COMPATIBLE indica ausência de rejeição ajustada nesta família; não prova aleatoriedade.",
        },
    }

    pairs = pair_tests(normalized_draws)
    pair_alerts = [item for item in pairs if item.p_holm < alpha]
    dimensions["cooccurrence"] = {
        "state": "ALERT" if pair_alerts else "COMPATIBLE",
        "evidence": {
            "method": "pair_binomial_two_sided",
            "family_size": len(pairs),
            "correction": "holm",
            "alpha": alpha,
            "alerts": len(pair_alerts),
            "min_adjusted_p": min(item.p_holm for item in pairs),
            "max_abs_effect": max(abs(item.effect) for item in pairs),
            "strongest": _strongest(pairs),
            "expected_pair_probability": 0.35,
        },
    }

    usable_lags = tuple(lag for lag in temporal_lags if 0 < lag < len(normalized_draws))
    if usable_lags:
        temporal = temporal_lag_permutation_tests(
            normalized_draws,
            lags=usable_lags,
            replications=temporal_replications,
            seed=temporal_seed,
        )
        temporal_alerts = [item for item in temporal if item.p_holm < alpha]
        dimensions["temporal"] = {
            "state": "ALERT" if temporal_alerts else "COMPATIBLE",
            "evidence": {
                "method": "complete_draw_row_permutation",
                "lags": [item.lag for item in temporal],
                "replications": temporal_replications,
                "seed": temporal_seed,
                "correction": "holm",
                "alpha": alpha,
                "alerts": len(temporal_alerts),
                "min_adjusted_p": min(item.p_holm for item in temporal),
                "max_abs_effect": max(abs(item.effect) for item in temporal),
                "statistics": [
                    {
                        "lag": item.lag,
                        "observed": item.observed,
                        "expected_permuted": item.expected,
                        "effect": item.effect,
                        "p_value": item.p_value,
                        "p_holm": item.p_holm,
                    }
                    for item in temporal
                ],
            },
        }
    else:
        dimensions["temporal"] = {
            "state": "INCONCLUSIVE",
            "evidence": {"reason": "Amostra insuficiente para os lags temporais predefinidos."},
        }

    if len(normalized_draws) >= 2:
        split_index = len(normalized_draws) // 2
        regime_stats = fixed_split_frequency_shift(normalized_draws, split_index=split_index)
        dimensions["regime"] = {
            "state": "INCONCLUSIVE",
            "evidence": {
                "diagnostic": "fixed_midpoint_frequency_shift",
                "split_index": split_index,
                "family_size": len(regime_stats),
                "correction": "holm",
                "min_adjusted_p": min(item.p_holm for item in regime_stats),
                "max_abs_effect": max(abs(item.effect) for item in regime_stats),
                "strongest": _strongest(regime_stats),
                "false_alarm_calibration": "NOT_ESTABLISHED",
                "reason": "Mudança de regime exige detector e taxa de falso alarme calibrados antes de STABLE/ALERT.",
            },
        }
    else:
        dimensions["regime"] = {
            "state": "INCONCLUSIVE",
            "evidence": {"reason": "Amostra insuficiente para diagnóstico de estabilidade."},
        }

    dimensions["predictive_evidence"] = {
        "state": predictive_state,
        "evidence": predictive_evidence,
    }

    return {
        "schema_version": RIS_SCHEMA_VERSION,
        "numeric_ris_enabled": False,
        "score": None,
        "snapshot_id": snapshot_id,
        "contest_count": len(normalized_draws),
        "alpha": alpha,
        "dimensions": dimensions,
        "guardrails": [
            "RIS_NUMERIC_FORBIDDEN_IN_1_X",
            "COMPATIBLE_IS_NOT_PROOF_OF_RANDOMNESS",
            "ALERT_IS_NOT_PREDICTIVE_ADVANTAGE",
            "NO_PREDICTIVE_ADVANTAGE_FROM_CATEGORICAL_STATUS",
        ],
    }


def build_categorical_ris(
    path: str | Path,
    *,
    alpha: float = DEFAULT_ALPHA,
    temporal_lags: tuple[int, ...] = DEFAULT_TEMPORAL_LAGS,
    temporal_replications: int = DEFAULT_TEMPORAL_REPLICATIONS,
    temporal_seed: int = DEFAULT_TEMPORAL_SEED,
) -> dict[str, Any]:
    """Constrói o RIS categórico para uma base SQLite reconstruída pelo SARE."""
    snapshots = list_snapshots(path)
    integrity = database_integrity(path)
    checks = verify_source_artifacts(path)
    invalid_artifacts = [check.artifact_id for check in checks if not check.valid]

    if integrity != "ok" or invalid_artifacts:
        data_state = "INVALID"
    elif snapshots and checks:
        data_state = "VERIFIED"
    else:
        data_state = "LIMITED"

    predictive_state, predictive_evidence = _predictive_state(path)
    data_evidence = {
        "database_integrity": integrity,
        "snapshots": len(snapshots),
        "source_artifacts": len(checks),
        "invalid_source_artifacts": invalid_artifacts,
    }

    if not snapshots:
        return build_categorical_ris_from_draws(
            (),
            snapshot_id=None,
            data_state=data_state,
            data_evidence=data_evidence,
            predictive_state=predictive_state,
            predictive_evidence=predictive_evidence,
            alpha=alpha,
            temporal_lags=temporal_lags,
            temporal_replications=temporal_replications,
            temporal_seed=temporal_seed,
        )

    snapshot = snapshots[0]
    snapshot_id = str(snapshot["snapshot_id"])
    draws = load_snapshot_draws(path, snapshot_id)
    return build_categorical_ris_from_draws(
        draws,
        snapshot_id=snapshot_id,
        data_state=data_state,
        data_evidence=data_evidence,
        predictive_state=predictive_state,
        predictive_evidence=predictive_evidence,
        alpha=alpha,
        temporal_lags=temporal_lags,
        temporal_replications=temporal_replications,
        temporal_seed=temporal_seed,
    )
