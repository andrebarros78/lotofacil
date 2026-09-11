from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ExperimentProtocol:
    hypothesis_id: str
    question: str
    h0: str
    h1: str
    snapshot_id: str
    metric_primary: str = "brier_score"
    baseline: str = "uniform_p_0_6"
    correction: str = "holm"
    evidence_mode: str = "RETROSPECTIVO_REVISADO"
    delta_min: float = 0.0
    min_train: int = 100
    variables: str = "marginal_presence_1_25"
    model: str = "M1_frequency_regularized_and_M2_exponential_vs_M0"
    comparators: tuple[str, ...] = ("uniform_p_0_6", "frequency_regularized", "exponential")
    multiplicity_family: str = "registered_primary_family_holm"
    sample_plan: str = "frozen_snapshot_walk_forward"
    stopping_rule: str = "fixed_snapshot_no_optional_stopping"
    code_environment: str = "release_commit_and_runtime_recorded_by_run"

    def validate(self) -> None:
        required = {
            "hypothesis_id": self.hypothesis_id,
            "question": self.question,
            "h0": self.h0,
            "h1": self.h1,
            "snapshot_id": self.snapshot_id,
            "metric_primary": self.metric_primary,
            "baseline": self.baseline,
            "variables": self.variables,
            "model": self.model,
            "multiplicity_family": self.multiplicity_family,
            "sample_plan": self.sample_plan,
            "stopping_rule": self.stopping_rule,
            "code_environment": self.code_environment,
        }
        empty = [name for name, value in required.items() if not str(value).strip()]
        if not self.comparators or any(not str(value).strip() for value in self.comparators):
            empty.append("comparators")
        if empty:
            raise ValueError(f"campos obrigatórios vazios: {', '.join(empty)}")
        if self.metric_primary != "brier_score":
            raise ValueError("Core 1.0 exige brier_score como métrica primária")
        if self.baseline != "uniform_p_0_6":
            raise ValueError("Core 1.0 exige baseline uniforme p=0,6")
        if self.correction != "holm":
            raise ValueError("Core 1.0 exige correção confirmatória Holm")
        if self.evidence_mode not in {"RETROSPECTIVO_REVISADO", "RETROSPECTIVO_COM_VINTAGE", "PROSPECTIVO"}:
            raise ValueError("evidence_mode inválido")
        if self.min_train <= 0:
            raise ValueError("min_train deve ser positivo")
        if self.delta_min < 0:
            raise ValueError("delta_min não pode ser negativo")
        if "uniform_p_0_6" not in self.comparators:
            raise ValueError("comparadores precisam incluir o M0 uniforme")

    def canonical_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def protocol_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
