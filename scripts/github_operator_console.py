from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_reports,
    render_post_contest_report_markdown,
)
from sare_lotofacil.analysis.ris import build_categorical_ris_from_draws
from sare_lotofacil.portfolios.authority import (
    POLICY_PRIMARY,
    STATUS_FROZEN,
    STATUS_PREVIEW,
    CardGenerationService,
    validate_card_artifact,
)
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL
from sare_lotofacil.portfolios.primary import (
    PRIMARY_MODEL_NAME,
    SECONDARY_MODEL_NAME,
    select_primary_card,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _state_summary(state_dir: Path) -> dict:
    latest = _load(state_dir / "latest.json")
    ledger = _load(state_dir / "prospective_ledger.json")
    return {
        "status": "GITHUB_OPERATOR_STATE_PASS",
        "official_latest_contest": latest["official_latest_contest"],
        "next_prediction_target": latest["next_prediction_target"],
        "snapshot_id": latest["snapshot_id"],
        "snapshot_hash": latest["snapshot_hash"],
        "storage_snapshot_id": latest.get("storage_snapshot_id", latest["snapshot_id"]),
        "storage_snapshot_hash": latest.get("storage_snapshot_hash", latest["snapshot_hash"]),
        "data_snapshot_hash": latest.get("data_snapshot_hash"),
        "database_integrity": latest["database_integrity"],
        "predictive_evidence": latest["prospective"]["predictive_evidence"],
        "prospective_state": latest["prospective"]["prospective_state"],
        "evaluated_predictions": ledger["summary"]["evaluated_predictions"],
        "pending_predictions": ledger["summary"]["pending_predictions"],
        "canonical_history_sha256": latest["canonical_history_sha256"],
        "prospective_ledger_sha256": _sha256(state_dir / "prospective_ledger.json"),
    }


def _analyze(state_dir: Path) -> dict:
    history = _load(state_dir / "canonical_history.json")
    ledger = _load(state_dir / "prospective_ledger.json")
    draws = tuple(tuple(record["numbers"]) for record in history["records"])
    report = analyze_core(draws)
    post_contest = build_post_contest_reports(ledger)
    return {
        "status": "GITHUB_OPERATOR_ANALYSIS_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contest_count": len(draws),
        "history_last_contest": history["records"][-1]["contest_id"],
        "canonical_history_sha256": _sha256(state_dir / "canonical_history.json"),
        "latest_post_contest_report": post_contest["latest_report"],
        "report": report.to_dict(),
    }


def _ris(state_dir: Path) -> dict:
    history = _load(state_dir / "canonical_history.json")
    latest = _load(state_dir / "latest.json")
    records = history["records"]
    draws = tuple(tuple(record["numbers"]) for record in records)
    candidate_labels = tuple(f"{record['contest_id']}:{record['draw_date']}" for record in records)
    prospective = latest["prospective"]
    prospective_state = str(prospective["prospective_state"])
    predictive_evidence = str(prospective["predictive_evidence"])
    if predictive_evidence == "REPLICATED":
        ris_predictive_state = "REPLICATED"
    elif prospective_state.startswith("UNDER_TEST"):
        ris_predictive_state = "UNDER_TEST"
    else:
        ris_predictive_state = "NOT_ESTABLISHED"

    panel = build_categorical_ris_from_draws(
        draws,
        snapshot_id=str(latest["snapshot_id"]),
        data_state="VERIFIED" if latest["database_integrity"] == "ok" else "INVALID",
        data_evidence={
            "database_integrity": latest["database_integrity"],
            "canonical_history_sha256": latest["canonical_history_sha256"],
            "history_file_sha256": _sha256(state_dir / "canonical_history.json"),
            "official_latest_contest": latest["official_latest_contest"],
            "source": "operations/state",
        },
        predictive_state=ris_predictive_state,
        predictive_evidence={
            "predictive_evidence": predictive_evidence,
            "prospective_state": prospective_state,
            "evaluated_predictions": prospective["evaluated_predictions"],
            "pending_predictions": prospective["pending_predictions"],
            "source": "operations/state/latest.json",
        },
        candidate_labels=candidate_labels,
    )
    return {
        "status": "GITHUB_OPERATOR_RIS_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **panel,
    }


def _primary_card(state_dir: Path) -> dict:
    latest = _load(state_dir / "latest.json")
    ledger = _load(state_dir / "prospective_ledger.json")
    target = int(latest["next_prediction_target"])
    prediction = next(
        (item for item in ledger.get("predictions", []) if int(item["target_contest"]) == target),
        None,
    )
    if prediction is None:
        raise RuntimeError("PRIMARY_CARD_FROZEN_PREDICTION_NOT_FOUND")
    models = prediction.get("models")
    if not isinstance(models, dict):
        raise RuntimeError("PRIMARY_CARD_FROZEN_MODELS_NOT_FOUND")
    try:
        primary_scores = models[PRIMARY_MODEL_NAME]
        secondary_scores = models[SECONDARY_MODEL_NAME]
    except KeyError as exc:
        raise RuntimeError("PRIMARY_CARD_REQUIRED_MODEL_NOT_FOUND") from exc

    decision = select_primary_card(
        primary_scores,
        secondary_scores,
        target_contest=target,
        training_last_contest=int(prediction["training_last_contest"]),
    )
    frozen = prediction.get("primary_card")
    if frozen is not None:
        if not isinstance(frozen, dict) or frozen.get("decision_sha256") != decision.decision_sha256:
            raise RuntimeError("PRIMARY_CARD_FROZEN_DECISION_MISMATCH")
        decision_source = "FROZEN_PRIMARY_CARD"
    else:
        decision_source = "DERIVED_FROM_FROZEN_LEGACY_MODEL_SCORES"

    artifact_payload = prediction.get("primary_card_artifact")
    if isinstance(artifact_payload, dict):
        validated_artifact = validate_card_artifact(
            artifact_payload,
            expected_status=STATUS_FROZEN,
            expected_cards=(decision.card,),
            require_operational=True,
        )
        if validated_artifact.policy_id != POLICY_PRIMARY:
            raise RuntimeError("PRIMARY_CARD_ARTIFACT_POLICY_MISMATCH")
        card_artifact = validated_artifact.to_dict()
    else:
        card_artifact = CardGenerationService.freeze_primary(
            card=decision.card,
            target_contest=target,
            training_last_contest=decision.training_last_contest,
            decision_sha256=decision.decision_sha256,
            primary_model=decision.primary_model,
            secondary_model=decision.secondary_model,
            selection_method=decision.selection_method,
            data_snapshot_hash=latest.get("data_snapshot_hash"),
            storage_snapshot_id=latest.get("storage_snapshot_id", latest.get("snapshot_id")),
            storage_snapshot_hash=latest.get("storage_snapshot_hash", latest.get("snapshot_hash")),
        ).to_dict()

    return {
        "status": "GITHUB_OPERATOR_PRIMARY_CARD_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "training_last_contest": decision.training_last_contest,
        "card_count": 1,
        "cost_cents": 350,
        "predictive_evidence": latest["prospective"]["predictive_evidence"],
        "evidence_label": decision.evidence_label,
        "state_snapshot_id": latest["snapshot_id"],
        "state_snapshot_hash": latest["snapshot_hash"],
        "storage_snapshot_id": latest.get("storage_snapshot_id", latest["snapshot_id"]),
        "storage_snapshot_hash": latest.get("storage_snapshot_hash", latest["snapshot_hash"]),
        "data_snapshot_hash": latest.get("data_snapshot_hash"),
        "selection_method": decision.selection_method,
        "primary_model": decision.primary_model,
        "secondary_model": decision.secondary_model,
        "primary_model_score_sum": decision.primary_model_score_sum,
        "secondary_model_score_sum": decision.secondary_model_score_sum,
        "decision_sha256": decision.decision_sha256,
        "decision_source": decision_source,
        "artifact_status": card_artifact["status"],
        "card_artifact": card_artifact,
        "card": list(decision.card),
        "card_display": " ".join(f"{number:02d}" for number in decision.card),
        "ranking": list(decision.ranking),
    }


def _portfolio(state_dir: Path, card_count: int, seed: int) -> dict:
    latest = _load(state_dir / "latest.json")
    target = int(latest["next_prediction_target"])
    effective_seed = target if seed == 0 else seed
    artifact = CardGenerationService.preview_uniform(
        card_count=card_count,
        seed=effective_seed,
        target_contest=target,
        data_snapshot_hash=latest.get("data_snapshot_hash"),
        storage_snapshot_id=latest.get("storage_snapshot_id", latest["snapshot_id"]),
        storage_snapshot_hash=latest.get("storage_snapshot_hash", latest["snapshot_hash"]),
    )
    if artifact.evidence_label != UNPROVEN_LABEL or artifact.status != STATUS_PREVIEW:
        raise RuntimeError("portfolio preview authority invariant violated")
    return {
        "status": "GITHUB_OPERATOR_PORTFOLIO_PREVIEW_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_status": artifact.status,
        "operational_use_allowed": artifact.operational_use_allowed,
        "card_artifact": artifact.to_dict(),
        "target_contest": target,
        "seed": artifact.seed,
        "card_count": artifact.card_count,
        "cost_cents": artifact.cost_cents,
        "predictive_evidence": artifact.predictive_evidence,
        "evidence_label": artifact.evidence_label,
        "state_snapshot_id": latest["snapshot_id"],
        "state_snapshot_hash": latest["snapshot_hash"],
        "storage_snapshot_id": latest.get("storage_snapshot_id", latest["snapshot_id"]),
        "storage_snapshot_hash": latest.get("storage_snapshot_hash", latest["snapshot_hash"]),
        "data_snapshot_hash": latest.get("data_snapshot_hash"),
        "cards": [list(card) for card in artifact.cards],
        "cards_display": [" ".join(f"{number:02d}" for number in card) for card in artifact.cards],
    }


def _export(state_dir: Path) -> tuple[dict, str]:
    summary = _state_summary(state_dir)
    latest = _load(state_dir / "latest.json")
    ledger = _load(state_dir / "prospective_ledger.json")
    state_names = ["bootstrap_manifest.json", "canonical_history.json", "prospective_ledger.json", "latest.json"]
    for optional_name in (
        "canonical_prizes.json",
        "post_contest_reports.json",
        "latest_post_contest_report.json",
    ):
        if (state_dir / optional_name).exists():
            state_names.append(optional_name)
    post_contest = build_post_contest_reports(ledger)
    payload = {
        "status": "GITHUB_OPERATOR_EXPORT_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "retrospective_core": latest["retrospective_core"],
        "prospective": latest["prospective"],
        "protocol": ledger["protocol"],
        "latest_post_contest_report": post_contest["latest_report"],
        "state_files": {name: _sha256(state_dir / name) for name in state_names},
    }
    md = "\n".join([
        "# SARE Lotofácil — Relatório Operacional GitHub",
        "",
        f"- concurso oficial mais recente: `{summary['official_latest_contest']}`",
        f"- próxima previsão: `{summary['next_prediction_target']}`",
        f"- estado prospectivo: `{summary['prospective_state']}`",
        f"- evidência preditiva: `{summary['predictive_evidence']}`",
        f"- previsões avaliadas: `{summary['evaluated_predictions']}`",
        f"- previsões pendentes: `{summary['pending_predictions']}`",
        f"- integridade do banco reconstruído: `{summary['database_integrity']}`",
        "",
        "**Não há promoção automática de vantagem preditiva.**",
        "",
    ])
    if post_contest["latest_report"] is not None:
        md += "\n" + render_post_contest_report_markdown(post_contest["latest_report"])
    return payload, md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only operator console for the canonical GitHub state")
    parser.add_argument(
        "--action",
        choices=("status", "audit", "analyze", "ris", "primary-card", "portfolio-preview", "portfolio", "export"),
        required=True,
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--card-count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.action in {"status", "audit"}:
        payload = _state_summary(args.state_dir)
        payload["action"] = args.action
        _write_json(args.out_dir / f"{args.action}.json", payload)
    elif args.action == "analyze":
        payload = _analyze(args.state_dir)
        _write_json(args.out_dir / "analysis.json", payload)
    elif args.action == "ris":
        payload = _ris(args.state_dir)
        _write_json(args.out_dir / "ris.json", payload)
    elif args.action == "primary-card":
        payload = _primary_card(args.state_dir)
        _write_json(args.out_dir / "primary_card.json", payload)
    elif args.action in {"portfolio-preview", "portfolio"}:
        payload = _portfolio(args.state_dir, args.card_count, args.seed)
        payload["action"] = "portfolio-preview"
        if args.action == "portfolio":
            payload["legacy_action_alias"] = "portfolio"
        _write_json(args.out_dir / "portfolio_preview.json", payload)
    elif args.action == "export":
        payload, md = _export(args.state_dir)
        _write_json(args.out_dir / "operational_report.json", payload)
        (args.out_dir / "operational_report.md").write_text(md, encoding="utf-8")
    else:  # pragma: no cover
        raise RuntimeError("unsupported action")

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
