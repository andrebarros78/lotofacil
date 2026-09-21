from __future__ import annotations

MANUAL_EVALUATION = "MANUAL_EVALUATION"
CANONICAL_EVALUATION = "CANONICAL_EVALUATION"
USER_SUPPLIED_SOURCE = "USER_SUPPLIED"


def evidence_eligible(evaluation_class: str) -> bool:
    if evaluation_class == CANONICAL_EVALUATION:
        return True
    if evaluation_class == MANUAL_EVALUATION:
        return False
    raise ValueError(f"evaluation_class inválida: {evaluation_class}")
