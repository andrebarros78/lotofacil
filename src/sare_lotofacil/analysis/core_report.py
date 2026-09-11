from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.models import WalkForwardResult, walk_forward_exponential, walk_forward_frequency
from sare_lotofacil.statistics.descriptive import marginal_uniformity, repetition_counts


@dataclass(frozen=True, slots=True)
class CoreAnalysisReport:
    contest_count: int
    min_train: int
    min_marginal_frequency: float
    max_marginal_frequency: float
    max_abs_marginal_z: float
    mean_consecutive_repetition: float | None
    m1_frequency: WalkForwardResult
    m2_exponential: WalkForwardResult
    predictive_evidence: str
    scientific_conclusion: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["m1_frequency"] = asdict(self.m1_frequency)
        payload["m2_exponential"] = asdict(self.m2_exponential)
        return payload


def analyze_core(draws: Sequence[Iterable[int]], *, min_train: int | None = None, delta_min: float = 0.0) -> CoreAnalysisReport:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if len(normalized) < 101:
        raise ValueError("Core requer ao menos 101 concursos para walk-forward")
    if delta_min < 0:
        raise ValueError("delta_min não pode ser negativo")
    selected_min_train = min_train if min_train is not None else max(100, int(len(normalized) * 0.60))
    if selected_min_train >= len(normalized):
        raise ValueError("min_train precisa ser menor que a quantidade de concursos")

    marginal = marginal_uniformity(normalized)
    repetitions = repetition_counts(normalized)
    m1 = walk_forward_frequency(normalized, min_train=selected_min_train, lam=100.0, delta_min=delta_min)
    m2 = walk_forward_exponential(normalized, min_train=selected_min_train, alpha=0.05, delta_min=delta_min)

    return CoreAnalysisReport(
        contest_count=len(normalized),
        min_train=selected_min_train,
        min_marginal_frequency=min(item.frequency for item in marginal),
        max_marginal_frequency=max(item.frequency for item in marginal),
        max_abs_marginal_z=max(abs(item.z_score) for item in marginal),
        mean_consecutive_repetition=fmean(repetitions) if repetitions else None,
        m1_frequency=m1,
        m2_exponential=m2,
        predictive_evidence="NOT_ESTABLISHED",
        scientific_conclusion="EVIDENCIA_PREDITIVA_INSUFICIENTE",
    )
