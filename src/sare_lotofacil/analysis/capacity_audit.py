from __future__ import annotations

from dataclasses import asdict
from statistics import fmean
from typing import Iterable, Sequence

from sare_lotofacil.experiments.backtest import (
    BacktestLeakageError,
    BacktestWindow,
    TemporalVariable,
    run_audited_backtest,
)
from sare_lotofacil.experiments.models import walk_forward_exponential, walk_forward_frequency
from sare_lotofacil.simulation.alternative import (
    simulate_marginal_bias,
    simulate_marginal_regime_shift,
    simulate_temporal_memory,
)
from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.regime import scan_marginal_regime_change


def _model_payload(result) -> dict[str, object]:
    return asdict(result)


def run_real_training_audit(
    draws: Sequence[Iterable[int]],
    *,
    min_train: int | None = None,
) -> dict[str, object]:
    """Executa M1/M2 em walk-forward sobre histórico real sem promover evidência."""
    total = len(draws)
    if total < 130:
        raise ValueError("REAL_TRAINING_AUDIT_REQUIRES_AT_LEAST_130_DRAWS")
    effective_min_train = min_train if min_train is not None else max(100, (total * 60) // 100)
    if total - effective_min_train < 30:
        raise ValueError("REAL_TRAINING_AUDIT_REQUIRES_AT_LEAST_30_EVALUATION_WINDOWS")

    m1 = walk_forward_frequency(draws, min_train=effective_min_train, lam=100.0)
    m2 = walk_forward_exponential(draws, min_train=effective_min_train, alpha=0.05)
    return {
        "protocol": "RETROSPECTIVE_REVISED_FIXED_BASELINES",
        "draw_count": total,
        "min_train": effective_min_train,
        "evaluation_windows": total - effective_min_train,
        "m0_brier": 0.24,
        "m1": _model_payload(m1),
        "m2": _model_payload(m2),
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
        "limitations": [
            "Auditoria retrospectiva; não constitui replicação prospectiva.",
            "Os intervalos atuais dos modelos usam aproximação normal por janela e não substituem análise por blocos quando houver dependência temporal relevante.",
        ],
    }


def _fault_injection_audit() -> dict[str, object]:
    windows = tuple(
        BacktestWindow(
            window_id=f"fault-{index}",
            training_last_contest=index,
            target_contest=index + 1,
            variables=(TemporalVariable("history", index),),
        )
        for index in range(1, 41)
    )

    def scorer(window: BacktestWindow) -> float:
        if window.target_contest % 5 == 0:
            raise RuntimeError("INJECTED_SCORER_FAILURE")
        return 0.24

    report = run_audited_backtest(
        windows,
        scorer,
        min_successful_windows=35,
        min_success_rate=0.90,
    )
    return {
        "status": report.status,
        "planned_windows": report.planned_windows,
        "successful_windows": report.successful_windows,
        "failed_windows": report.failed_windows,
        "success_rate": report.success_rate,
        "failed_are_preserved": report.failed_windows == 8,
        "low_coverage_is_inconclusive": report.status == "INCONCLUSIVE",
    }


def _leakage_injection_blocked() -> bool:
    leaking = (
        BacktestWindow(
            window_id="leak-1",
            training_last_contest=100,
            target_contest=101,
            variables=(TemporalVariable("future_result", 101),),
        ),
    )
    try:
        run_audited_backtest(leaking, lambda _: 0.24, min_successful_windows=1, min_success_rate=1.0)
    except BacktestLeakageError:
        return True
    return False


def run_synthetic_capacity_audit() -> dict[str, object]:
    """Qualifica detectores/modelos contra nulo e alternativas controladas."""
    null_deltas_m1: list[float] = []
    null_deltas_m2: list[float] = []
    for seed in (2026091501, 2026091502, 2026091503):
        null_draws = simulate_uniform_draws(500, seed=seed).draws
        null_deltas_m1.append(walk_forward_frequency(null_draws, min_train=150).delta_brier)
        null_deltas_m2.append(walk_forward_exponential(null_draws, min_train=150).delta_brier)

    bias_draws = simulate_marginal_bias(
        800,
        target_number=16,
        target_probability=0.85,
        seed=2026091511,
    ).draws
    bias_m1 = walk_forward_frequency(bias_draws, min_train=200)

    memory_draws = simulate_temporal_memory(
        800,
        memory_probability=0.90,
        retained_count=13,
        seed=2026091512,
    ).draws
    memory_m2 = walk_forward_exponential(memory_draws, min_train=200)

    regime = simulate_marginal_regime_shift(
        800,
        change_index=400,
        target_number=16,
        post_probability=0.95,
        seed=2026091513,
    )
    regime_scan = scan_marginal_regime_change(regime.draws, min_segment=100, candidate_stride=10)

    reproducible_a = simulate_uniform_draws(250, seed=2026091514).draws
    reproducible_b = simulate_uniform_draws(250, seed=2026091514).draws
    fault = _fault_injection_audit()
    leakage_blocked = _leakage_injection_blocked()

    null_mean_m1 = fmean(null_deltas_m1)
    null_mean_m2 = fmean(null_deltas_m2)
    gates = {
        "null_m1_no_large_systematic_gain": null_mean_m1 < 0.01,
        "null_m2_no_large_systematic_gain": null_mean_m2 < 0.01,
        "marginal_bias_detected_by_m1": bias_m1.delta_brier > 0.0,
        "temporal_memory_detected_by_m2": memory_m2.delta_brier > 0.0,
        "regime_change_localized": abs(regime_scan.strongest.candidate_index - regime.change_index) <= 50,
        "regime_target_identified": regime_scan.strongest.strongest_number == regime.target_number,
        "same_seed_is_reproducible": reproducible_a == reproducible_b,
        "lookahead_is_blocked": leakage_blocked,
        "faults_remain_in_denominator": bool(fault["failed_are_preserved"]),
        "insufficient_success_is_inconclusive": bool(fault["low_coverage_is_inconclusive"]),
    }
    failed_gates = tuple(name for name, passed in gates.items() if not passed)
    return {
        "status": "PASS" if not failed_gates else "FAIL",
        "gates": gates,
        "failed_gates": failed_gates,
        "null": {
            "m1_deltas": null_deltas_m1,
            "m2_deltas": null_deltas_m2,
            "m1_mean_delta": null_mean_m1,
            "m2_mean_delta": null_mean_m2,
        },
        "marginal_bias": _model_payload(bias_m1),
        "temporal_memory": _model_payload(memory_m2),
        "regime_change": {
            "expected_index": regime.change_index,
            "detected_index": regime_scan.strongest.candidate_index,
            "expected_number": regime.target_number,
            "detected_number": regime_scan.strongest.strongest_number,
            "max_abs_z": regime_scan.statistic,
        },
        "fault_injection": fault,
        "lookahead_blocked": leakage_blocked,
        "reproducibility": reproducible_a == reproducible_b,
    }
