from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any, Iterable, Sequence

from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.regime import MarginalRegimeScan, scan_marginal_regime_change


DEFAULT_REGIME_ALPHA = 0.05
DEFAULT_REGIME_MIN_SEGMENT = 100
DEFAULT_REGIME_CANDIDATE_STRIDE = 10
DEFAULT_REGIME_CALIBRATION_REPLICATIONS = 199
DEFAULT_REGIME_VALIDATION_REPLICATIONS = 199
DEFAULT_REGIME_SEED = 20260914


@dataclass(frozen=True, slots=True)
class FalseAlarmCalibration:
    target_alpha: float
    threshold: float
    calibration_replications: int
    validation_replications: int
    validation_false_alarms: int
    validation_false_alarm_rate: float
    validation_ci95_low: float
    validation_ci95_high: float
    compatible_with_target: bool
    seed: int


@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    state: str
    scan: MarginalRegimeScan
    calibration: FalseAlarmCalibration
    monte_carlo_p_value: float
    mode: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        strongest = asdict(self.scan.strongest)
        candidate_points = [asdict(item) for item in self.scan.candidates]
        return {
            "state": self.state,
            "method": "calibrated_global_marginal_change_scan",
            "mode": self.mode,
            "reason": self.reason,
            "observed_statistic": self.scan.statistic,
            "monte_carlo_p_value": self.monte_carlo_p_value,
            "min_segment": self.scan.min_segment,
            "candidate_stride": self.scan.candidate_stride,
            "candidate_count": len(self.scan.candidates),
            "candidate_points": candidate_points,
            "strongest_candidate": strongest,
            "false_alarm_calibration": asdict(self.calibration),
            "interpretation": (
                "STABLE significa ausência de alerta neste detector calibrado; não prova estabilidade física. "
                "ALERT identifica mudança estatística retrospectiva candidata; não estabelece causa nem vantagem preditiva."
            ),
        }


def _wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials <= 0:
        raise ValueError("trials deve ser positivo")
    if not 0 <= successes <= trials:
        raise ValueError("successes fora do intervalo")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence deve estar entre 0 e 1")
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def _calibrate_with_distribution(
    contest_count: int,
    *,
    alpha: float,
    min_segment: int,
    candidate_stride: int,
    calibration_replications: int,
    validation_replications: int,
    seed: int,
) -> tuple[FalseAlarmCalibration, tuple[float, ...]]:
    if contest_count < 2 * min_segment:
        raise ValueError("amostra insuficiente para calibrar regime")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha deve estar entre 0 e 1")
    if calibration_replications < 20 or validation_replications < 20:
        raise ValueError("calibração e validação exigem ao menos 20 replicações cada")

    rng = random.Random(seed)
    calibration_stats: list[float] = []
    for _ in range(calibration_replications):
        simulation_seed = rng.randrange(0, 2**63)
        null_draws = simulate_uniform_draws(contest_count, seed=simulation_seed).draws
        scan = scan_marginal_regime_change(
            null_draws,
            min_segment=min_segment,
            candidate_stride=candidate_stride,
        )
        calibration_stats.append(scan.statistic)

    calibration_stats.sort()
    rank = math.ceil((1.0 - alpha) * (calibration_replications + 1))
    threshold = math.inf if rank > calibration_replications else calibration_stats[rank - 1]

    false_alarms = 0
    for _ in range(validation_replications):
        simulation_seed = rng.randrange(0, 2**63)
        null_draws = simulate_uniform_draws(contest_count, seed=simulation_seed).draws
        scan = scan_marginal_regime_change(
            null_draws,
            min_segment=min_segment,
            candidate_stride=candidate_stride,
        )
        if scan.statistic >= threshold:
            false_alarms += 1

    rate = false_alarms / validation_replications
    ci_low, ci_high = _wilson_interval(false_alarms, validation_replications)
    compatible = ci_low <= alpha <= ci_high
    calibration = FalseAlarmCalibration(
        target_alpha=alpha,
        threshold=threshold,
        calibration_replications=calibration_replications,
        validation_replications=validation_replications,
        validation_false_alarms=false_alarms,
        validation_false_alarm_rate=rate,
        validation_ci95_low=ci_low,
        validation_ci95_high=ci_high,
        compatible_with_target=compatible,
        seed=seed,
    )
    return calibration, tuple(calibration_stats)


def assess_marginal_regime(
    draws: Sequence[Iterable[int]],
    *,
    candidate_labels: Sequence[str] | None = None,
    alpha: float = DEFAULT_REGIME_ALPHA,
    min_segment: int = DEFAULT_REGIME_MIN_SEGMENT,
    candidate_stride: int = DEFAULT_REGIME_CANDIDATE_STRIDE,
    calibration_replications: int = DEFAULT_REGIME_CALIBRATION_REPLICATIONS,
    validation_replications: int = DEFAULT_REGIME_VALIDATION_REPLICATIONS,
    seed: int = DEFAULT_REGIME_SEED,
) -> RegimeAssessment:
    """Avalia mudança de regime com calibração/validação nulas independentes.

    O detector é retrospectivo. Nenhum ALERT desta função deve ser descrito como
    alerta emitido em tempo real ou como evidência preditiva.
    """
    scan = scan_marginal_regime_change(
        draws,
        candidate_labels=candidate_labels,
        min_segment=min_segment,
        candidate_stride=candidate_stride,
    )
    calibration, calibration_stats = _calibrate_with_distribution(
        len(draws),
        alpha=alpha,
        min_segment=min_segment,
        candidate_stride=candidate_stride,
        calibration_replications=calibration_replications,
        validation_replications=validation_replications,
        seed=seed,
    )
    exceedances = sum(value >= scan.statistic for value in calibration_stats)
    monte_carlo_p = (1.0 + exceedances) / (calibration_replications + 1.0)

    if not calibration.compatible_with_target:
        state = "INCONCLUSIVE"
        reason = "A validação nula independente não confirmou a taxa de falso alarme alvo dentro do IC95%."
    elif scan.statistic >= calibration.threshold and monte_carlo_p <= alpha:
        state = "ALERT"
        reason = "O máximo observado excedeu o limiar global calibrado e o p Monte Carlo ficou no nível predefinido."
    else:
        state = "STABLE"
        reason = "Nenhuma mudança excedeu o limiar global após calibração independente do falso alarme."

    return RegimeAssessment(
        state=state,
        scan=scan,
        calibration=calibration,
        monte_carlo_p_value=monte_carlo_p,
        mode="RETROSPECTIVE_DISCOVERY",
        reason=reason,
    )
