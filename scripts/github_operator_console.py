from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.analysis.ris import build_categorical_ris_from_draws
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL, generate_uniform_portfolio


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
    draws = tuple(tuple(record["numbers"]) for record in history["records"])
    report = analyze_core(draws)
    return {
        "status": "GITHUB_OPERATOR_ANALYSIS_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contest_count": len(draws),
        "history_last_contest": history["records"][-1]["contest_id"],
        "canonical_history_sha256": _sha256(state_dir / "canonical_history.json"),
        "report": report.to_dict(),
    }


def _ris(state_dir: Path) -> dict:
    history = _load(state_dir / "canonical_history.json")
    latest = _load(state_dir / "latest.json")
    draws = tuple(tuple(record["numbers"]) for record in history["records"])
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
    )
    return {
        "status": "GITHUB_OPERATOR_RIS_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **panel,
    }


def _portfolio(state_dir: Path, card_count: int, seed: int) -> dict:
    latest = _load(state_dir / "latest.json")
    target = int(latest["next_prediction_target"])
    effective_seed = target if seed == 0 else seed
    portfolio = generate_uniform_portfolio(card_count, seed=effective_seed)
    if portfolio.evidence_label != UNPROVEN_LABEL:
        raise RuntimeError("portfolio evidence label invariant violated")
    return {
        "status": "GITHUB_OPERATOR_PORTFOLIO_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_contest": target,
        "seed": portfolio.seed,
        "card_count": len(portfolio.cards),
        "cost_cents": portfolio.cost_cents,
        "predictive_evidence": latest["prospective"]["predictive_evidence"],
        "evidence_label": portfolio.evidence_label,
        "state_snapshot_id": latest["snapshot_id"],
        "state_snapshot_hash": latest["snapshot_hash"],
        "cards": [list(card) for card in portfolio.cards],
        "cards_display": [" ".join(f"{number:02d}" for number in card) for card in portfolio.cards],
    }


def _export(state_dir: Path) -> tuple[dict, str]:
    summary = _state_summary(state_dir)
    latest = _load(state_dir / "latest.json")
    ledger = _load(state_dir / "prospective_ledger.json")
    state_names = ["bootstrap_manifest.json", "canonical_history.json", "prospective_ledger.json", "latest.json"]
    if (state_dir / "canonical_prizes.json").exists():
        state_names.append("canonical_prizes.json")
    payload = {
        "status": "GITHUB_OPERATOR_EXPORT_PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "retrospective_core": latest["retrospective_core"],
        "prospective": latest["prospective"],
        "protocol": ledger["protocol"],
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
    return payload, md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only operator console for the canonical GitHub state")
    parser.add_argument("--action", choices=("status", "audit", "analyze", "ris", "portfolio", "export"), required=True)
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
    elif args.action == "portfolio":
        payload = _portfolio(args.state_dir, args.card_count, args.seed)
        _write_json(args.out_dir / "portfolio.json", payload)
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
