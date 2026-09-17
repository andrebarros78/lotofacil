from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from sare_lotofacil.experiments.models import WalkForwardResult, walk_forward_frequency


class ChallengerLeakageError(RuntimeError):
    """Raised when hypothesis or validation boundaries would leak future/lockbox data."""


@dataclass(frozen=True, slots=True)
class ChallengerHypothesis:
    hypothesis_id: str
    source_episode_id: str
    source_contest: int
    statement: str
    expected_mechanism: str
    metric_primary: str
    baseline: str
    validation_start_contest: int
    validation_end_contest: int
    stop_rule: str
    promotion_rule: str
    prohibited_selection_data: tuple[str, ...]
    challenger_model: str = "frequency_regularized"
    challenger_lam: float = 50.0
    delta_min: float = 0.0

    def validate(self) -> None:
        required = {
            "hypothesis_id": self.hypothesis_id,
            "source_episode_id": self.source_episode_id,
            "statement": self.statement,
            "expected_mechanism": self.expected_mechanism,
            "metric_primary": self.metric_primary,
            "baseline": self.baseline,
            "stop_rule": self.stop_rule,
            "promotion_rule": self.promotion_rule,
        }
        empty = [name for name, value in required.items() if not str(value).strip()]
        if empty:
            raise ValueError(f"campos obrigatórios vazios: {', '.join(empty)}")
        if self.source_contest <= 0:
            raise ValueError("source_contest deve ser positivo")
        if self.validation_start_contest <= self.source_contest:
            raise ChallengerLeakageError("VALIDATION_MUST_START_AFTER_HYPOTHESIS_SOURCE_CONTEST")
        if self.validation_end_contest < self.validation_start_contest:
            raise ValueError("validation_end_contest deve ser >= validation_start_contest")
        if self.metric_primary != "brier_score":
            raise ValueError("R2 exige brier_score como métrica primária")
        if self.baseline != "uniform_p_0_6":
            raise ValueError("R2 exige M0 uniforme p=0,6")
        if self.stop_rule != "fixed_validation_window_no_optional_stopping":
            raise ValueError("R2 exige janela fixa sem optional stopping")
        if self.promotion_rule != "challenger_ci_low_gt_delta_min_and_brier_lt_champion":
            raise ValueError("regra de promoção R2 inválida")
        required_prohibited = {"future_results", "validation_targets", "prospective_lockbox"}
        if not required_prohibited.issubset(set(self.prohibited_selection_data)):
            raise ValueError("dados proibidos mínimos ausentes")
        if self.challenger_model != "frequency_regularized":
            raise ValueError("challenger_model não suportado")
        if self.challenger_lam < 0:
            raise ValueError("challenger_lam deve ser não negativo")
        if self.delta_min < 0:
            raise ValueError("delta_min deve ser não negativo")

    @property
    def hypothesis_hash(self) -> str:
        self.validate()
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChampionConfig:
    model_name: str = "M1_frequency_regularized_lambda_100"
    lam: float = 100.0

    @property
    def config_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChallengerDecision:
    hypothesis_id: str
    hypothesis_hash: str
    champion_hash_before: str
    champion_hash_after: str
    champion_result: WalkForwardResult
    challenger_result: WalkForwardResult
    decision: str
    reason: str
    promotion_applied: bool
    predictive_evidence: str

    @property
    def content_hash(self) -> str:
        payload = {
            **asdict(self),
            "champion_result": asdict(self.champion_result),
            "challenger_result": asdict(self.challenger_result),
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def build_hypothesis_from_episode(
    episode: dict[str, object],
    *,
    hypothesis_id: str,
    statement: str,
    expected_mechanism: str,
    validation_start_contest: int,
    validation_end_contest: int,
    challenger_lam: float,
    delta_min: float = 0.0,
) -> ChallengerHypothesis:
    policy = episode.get("learning_policy")
    if not isinstance(policy, dict):
        raise ValueError("episódio sem learning_policy")
    if policy.get("retrospective_only") is not True:
        raise RuntimeError("EPISODE_NOT_RETROSPECTIVE_ONLY")
    if policy.get("rewrite_frozen_cards") is not False:
        raise RuntimeError("EPISODE_ALLOWS_FREEZE_REWRITE")
    if policy.get("direct_model_tuning_allowed") is not False:
        raise RuntimeError("EPISODE_ALLOWS_DIRECT_MODEL_TUNING")
    contest_id = int(episode["contest_id"])
    episode_id = str(episode["episode_id"])
    hypothesis = ChallengerHypothesis(
        hypothesis_id=hypothesis_id,
        source_episode_id=episode_id,
        source_contest=contest_id,
        statement=statement,
        expected_mechanism=expected_mechanism,
        metric_primary="brier_score",
        baseline="uniform_p_0_6",
        validation_start_contest=validation_start_contest,
        validation_end_contest=validation_end_contest,
        stop_rule="fixed_validation_window_no_optional_stopping",
        promotion_rule="challenger_ci_low_gt_delta_min_and_brier_lt_champion",
        prohibited_selection_data=("future_results", "validation_targets", "prospective_lockbox"),
        challenger_lam=challenger_lam,
        delta_min=delta_min,
    )
    hypothesis.validate()
    return hypothesis


def _slice_for_validation(draws: Sequence[Iterable[int]], hypothesis: ChallengerHypothesis) -> tuple[Iterable[int], ...]:
    if hypothesis.validation_end_contest > len(draws):
        raise RuntimeError("VALIDATION_RESULTS_NOT_AVAILABLE")
    return tuple(draws[: hypothesis.validation_end_contest])


def run_isolated_challenger(
    draws: Sequence[Iterable[int]],
    *,
    hypothesis: ChallengerHypothesis,
    champion: ChampionConfig = ChampionConfig(),
) -> ChallengerDecision:
    hypothesis.validate()
    before_hash = champion.config_hash
    validation_draws = _slice_for_validation(draws, hypothesis)
    min_train = hypothesis.validation_start_contest - 1
    if min_train < 100:
        raise ValueError("R2 exige ao menos 100 concursos anteriores à validação")

    champion_result = walk_forward_frequency(
        validation_draws,
        min_train=min_train,
        lam=champion.lam,
        delta_min=hypothesis.delta_min,
    )
    challenger_result = walk_forward_frequency(
        validation_draws,
        min_train=min_train,
        lam=hypothesis.challenger_lam,
        delta_min=hypothesis.delta_min,
    )

    eligible = (
        challenger_result.backtest_status == "VALID"
        and champion_result.backtest_status == "VALID"
        and challenger_result.delta_brier_ci_low > hypothesis.delta_min
        and challenger_result.mean_brier < champion_result.mean_brier
    )
    if eligible:
        decision = "ELIGIBLE_FOR_PROMOTION"
        reason = "PREDECLARED_PROMOTION_RULE_SATISFIED"
    else:
        decision = "REJECTED"
        reason = "PREDECLARED_PROMOTION_RULE_NOT_SATISFIED"

    after_hash = champion.config_hash
    if before_hash != after_hash:
        raise RuntimeError("CHAMPION_MUTATION_DETECTED")

    return ChallengerDecision(
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_hash=hypothesis.hypothesis_hash,
        champion_hash_before=before_hash,
        champion_hash_after=after_hash,
        champion_result=champion_result,
        challenger_result=challenger_result,
        decision=decision,
        reason=reason,
        promotion_applied=False,
        predictive_evidence="NOT_ESTABLISHED",
    )
