from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REPORT_VERSION = "constructive-post-contest-v1"


def _numbers(value: object, *, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"POST_CONTEST_{field.upper()}_MISSING")
    numbers = tuple(sorted(int(number) for number in value))
    if len(numbers) != 15 or len(set(numbers)) != 15:
        raise RuntimeError(f"POST_CONTEST_{field.upper()}_INVALID")
    if any(number < 1 or number > 25 for number in numbers):
        raise RuntimeError(f"POST_CONTEST_{field.upper()}_OUT_OF_RANGE")
    return numbers


def _display(numbers: tuple[int, ...]) -> str:
    return " ".join(f"{number:02d}" for number in numbers)


def build_post_contest_report(prediction: Mapping[str, Any]) -> dict[str, Any]:
    evaluation = prediction.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise RuntimeError("POST_CONTEST_EVALUATION_MISSING")
    contest_number = int(prediction["target_contest"])
    observed_contest = int(evaluation.get("observed_contest", 0))
    if observed_contest != contest_number:
        raise RuntimeError("POST_CONTEST_CONTEST_MISMATCH")

    result = _numbers(evaluation.get("observed_numbers"), field="result")
    primary_card = prediction.get("primary_card")
    process_errors: list[str] = []
    corrections: list[str] = []
    adjustments: list[str] = []
    implementations: list[str] = [
        "Emitir e persistir este relatório automaticamente após cada resultado oficial avaliado.",
        "Acumular padrões de erro em vários concursos antes de propor qualquer alteração do modelo.",
    ]

    if not isinstance(primary_card, Mapping) or not isinstance(primary_card.get("card"), list):
        process_errors.append("PRIMARY_CARD_NOT_FROZEN_FOR_EVALUATED_CONTEST")
        corrections.append(
            "Garantir que toda previsão prospectiva nova congele o cartão primário antes do sorteio."
        )
        adjustments.append(
            "Não reconstruir retroativamente um cartão ausente usando o resultado já conhecido."
        )
        return {
            "schema_version": 1,
            "report_version": REPORT_VERSION,
            "status": "POST_CONTEST_REPORT_PASS_WITH_PROCESS_GAP",
            "contest_number": contest_number,
            "result": list(result),
            "result_display": _display(result),
            "generated_card": None,
            "generated_card_display": None,
            "hits": None,
            "matched_numbers": [],
            "selected_misses": [],
            "omitted_winners": [],
            "primary_delta_brier_vs_uniform": None,
            "self_analysis": {
                "process_errors": process_errors,
                "process_findings": ["Resultado oficial disponível, mas não existe cartão primário congelado."],
                "corrections_required": corrections,
                "adjustments_suggested": adjustments,
                "implementations_suggested": implementations,
            },
            "guardrails": [
                "FROZEN_CARD_IMMUTABLE",
                "NO_RETROACTIVE_CARD_RECONSTRUCTION",
                "NO_SINGLE_CONTEST_RETUNING",
            ],
        }

    card = _numbers(primary_card.get("card"), field="generated_card")
    result_set = set(result)
    card_set = set(card)
    matched = tuple(sorted(result_set & card_set))
    selected_misses = tuple(sorted(card_set - result_set))
    omitted_winners = tuple(sorted(result_set - card_set))
    hits = len(matched)

    card_evaluation = prediction.get("primary_card_evaluation")
    if not isinstance(card_evaluation, Mapping):
        process_errors.append("PRIMARY_CARD_EVALUATION_MISSING")
        corrections.append("Persistir a avaliação do cartão primário junto com a avaliação do concurso.")
    else:
        if int(card_evaluation.get("observed_contest", 0)) != contest_number:
            raise RuntimeError("POST_CONTEST_CARD_EVALUATION_CONTEST_MISMATCH")
        if int(card_evaluation.get("hits", -1)) != hits:
            raise RuntimeError("POST_CONTEST_HIT_MISMATCH")

    delta_brier = evaluation.get("delta_brier")
    primary_delta = None
    if isinstance(delta_brier, Mapping):
        value = delta_brier.get("M1_frequency_regularized_lambda_100")
        if isinstance(value, (int, float)):
            primary_delta = float(value)

    findings = [
        f"Cartão obteve {hits} acertos; {len(selected_misses)} selecionadas não saíram e "
        f"{len(omitted_winners)} sorteadas ficaram fora."
    ]
    adjustments.append(
        "Examinar a recorrência das dezenas selecionadas que não saíram e das sorteadas que ficaram fora "
        "em uma janela prospectiva; um único concurso não deve virar regra de seleção."
    )
    if primary_delta is not None and primary_delta < 0:
        findings.append("O modelo primário ficou abaixo do baseline uniforme neste concurso.")
        adjustments.append(
            "Se a perda para o baseline persistir na coorte, abrir challenger predeclarado e compará-lo "
            "sem alterar retroativamente o champion."
        )
    elif primary_delta is not None and primary_delta > 0:
        findings.append("O modelo primário superou o baseline uniforme neste concurso isolado.")
        adjustments.append(
            "Registrar o ganho sem promover o modelo; aguardar evidência prospectiva acumulada."
        )
    elif primary_delta == 0:
        findings.append("O modelo primário empatou com o baseline uniforme neste concurso.")

    if not corrections:
        corrections.append("Nenhuma correção de integridade obrigatória foi identificada neste ciclo.")

    return {
        "schema_version": 1,
        "report_version": REPORT_VERSION,
        "status": "POST_CONTEST_REPORT_PASS",
        "contest_number": contest_number,
        "result": list(result),
        "result_display": _display(result),
        "generated_card": list(card),
        "generated_card_display": _display(card),
        "hits": hits,
        "matched_numbers": list(matched),
        "selected_misses": list(selected_misses),
        "omitted_winners": list(omitted_winners),
        "primary_delta_brier_vs_uniform": primary_delta,
        "self_analysis": {
            "process_errors": process_errors,
            "process_findings": findings,
            "corrections_required": corrections,
            "adjustments_suggested": adjustments,
            "implementations_suggested": implementations,
        },
        "guardrails": [
            "FROZEN_CARD_IMMUTABLE",
            "NO_SINGLE_CONTEST_RETUNING",
            "CHALLENGER_REQUIRES_PREDECLARED_VALIDATION",
        ],
    }


def build_post_contest_reports(ledger: Mapping[str, Any]) -> dict[str, Any]:
    reports = [
        build_post_contest_report(prediction)
        for prediction in ledger.get("predictions", [])
        if isinstance(prediction, Mapping) and isinstance(prediction.get("evaluation"), Mapping)
    ]
    reports.sort(key=lambda report: int(report["contest_number"]))
    return {
        "schema_version": 1,
        "report_version": REPORT_VERSION,
        "reports": reports,
        "report_count": len(reports),
        "latest_contest": reports[-1]["contest_number"] if reports else None,
        "latest_report": reports[-1] if reports else None,
    }


def render_post_contest_report_markdown(report: Mapping[str, Any]) -> str:
    analysis = report["self_analysis"]
    card = report.get("generated_card_display") or "NÃO DISPONÍVEL — cartão primário não congelado"
    hits = report.get("hits")
    hits_text = str(hits) if hits is not None else "NÃO DISPONÍVEL"
    lines = [
        "# Análise Pós-Concurso — Lotofácil Operacional",
        "",
        f"- Concurso Número: {report['contest_number']}",
        f"- Resultado: {report['result_display']}",
        f"- Cartão gerado: {card}",
        f"- Número de acertos: {hits_text}",
        "",
        f"- Acertos: {_display(tuple(report.get('matched_numbers', [])))}",
        f"- Selecionadas que não saíram: {_display(tuple(report.get('selected_misses', [])))}",
        f"- Sorteadas que ficaram fora: {_display(tuple(report.get('omitted_winners', [])))}",
        "",
        "## Autoanálise do processo",
    ]
    lines.extend(f"- {item}" for item in analysis["process_findings"])
    if analysis["process_errors"]:
        lines.extend(["", "### Erros/Falhas identificados"])
        lines.extend(f"- {item}" for item in analysis["process_errors"])
    lines.extend(["", "### Correções necessárias"])
    lines.extend(f"- {item}" for item in analysis["corrections_required"])
    lines.extend(["", "### Ajustes sugeridos"])
    lines.extend(f"- {item}" for item in analysis["adjustments_suggested"])
    lines.extend(["", "### Implementações necessárias"])
    lines.extend(f"- {item}" for item in analysis["implementations_suggested"])
    lines.extend([
        "",
        "### Restrições",
        "- O cartão congelado não pode ser reescrito após o resultado.",
        "- Um único concurso não autoriza retuning nem promoção de modelo.",
        "",
    ])
    return "\n".join(lines)
