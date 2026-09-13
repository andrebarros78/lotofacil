from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.domain.combinatorics import (
    draw_sum_mean,
    draw_sum_variance,
    exact_hit_distribution,
    expected_hits,
    pair_probability,
    triple_probability,
    variance_hits,
)
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.ingestion.legacy_markdown import parse_legacy_markdown
from sare_lotofacil.persistence.backup import backup_database, restore_database
from sare_lotofacil.persistence.db import initialize_database
from sare_lotofacil.persistence.evidence import verify_source_artifacts
from sare_lotofacil.persistence.jobs import run_worker_once
from sare_lotofacil.persistence.repository import create_latest_snapshot, load_snapshot_draws, persist_caixa_contest
from sare_lotofacil.persistence.vintages import create_snapshot_as_of
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER


def doctor() -> int:
    distribution = exact_hit_distribution()
    checks = {
        "combination_space": DEFAULT_RULES.combination_space == 3_268_760,
        "distribution_sum": sum(distribution.values()) == 1,
        "expected_hits": expected_hits() == 9,
        "variance_hits": variance_hits() == Fraction(3, 2),
        "pair_probability": pair_probability() == Fraction(7, 20),
        "triple_probability": triple_probability() == Fraction(91, 460),
        "draw_sum_mean": draw_sum_mean() == 195,
        "draw_sum_variance": draw_sum_variance() == 325,
        "uniform_brier": abs(UNIFORM_BRIER - 0.24) < 1e-12,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("MATHEMATICAL_CHECKS_FAIL")
        for name in failed:
            print(f"FAIL: {name}")
        return 1
    print("MATHEMATICAL_CHECKS_PASS")
    print(f"combination_space={DEFAULT_RULES.combination_space}")
    print(f"uniform_brier={UNIFORM_BRIER:.12f}")
    return 0


def _load_legacy_file(path: Path):
    result = parse_legacy_markdown(path.read_text(encoding="utf-8"))
    if result.issues:
        for issue in result.issues:
            prefix = f"line={issue.line_number}" if issue.line_number else "global"
            print(f"IMPORT_ERROR {prefix} message={issue.message}")
        return None
    return result.records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sare-lotofacil")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="verifica invariantes matemáticos do Core")

    init_db = subparsers.add_parser("init-db", help="inicializa o banco SQLite local")
    init_db.add_argument("--path", type=Path, required=True)

    fetch = subparsers.add_parser("fetch-caixa", help="captura um concurso na fonte CAIXA e persiste sua revisão")
    fetch.add_argument("--db", type=Path, required=True)
    fetch.add_argument("--contest", type=int)

    snapshot = subparsers.add_parser("snapshot", help="publica snapshot das revisões mais recentes")
    snapshot.add_argument("--db", type=Path, required=True)

    snapshot_as_of = subparsers.add_parser(
        "snapshot-as-of",
        help="publica snapshot point-in-time usando somente revisões já disponíveis no cutoff",
    )
    snapshot_as_of.add_argument("--db", type=Path, required=True)
    snapshot_as_of.add_argument(
        "--availability-cutoff",
        required=True,
        help="timestamp ISO 8601 com timezone, por exemplo 2026-09-13T17:00:00-03:00",
    )

    analyze_snapshot = subparsers.add_parser("analyze-snapshot", help="executa relatório Core sobre snapshot publicado")
    analyze_snapshot.add_argument("--db", type=Path, required=True)
    analyze_snapshot.add_argument("--snapshot", required=True)
    analyze_snapshot.add_argument("--min-train", type=int)

    validate_history = subparsers.add_parser("validate-history", help="valida histórico legado em Markdown")
    validate_history.add_argument("--path", type=Path, required=True)

    analyze_history = subparsers.add_parser("analyze-history", help="executa relatório Core sobre histórico Markdown válido")
    analyze_history.add_argument("--path", type=Path, required=True)
    analyze_history.add_argument("--min-train", type=int)

    backup = subparsers.add_parser("backup-db", help="cria backup SQLite consistente e verificado")
    backup.add_argument("--db", type=Path, required=True)
    backup.add_argument("--out", type=Path, required=True)

    restore = subparsers.add_parser("restore-db", help="restaura backup SQLite para novo destino")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--out", type=Path, required=True)

    worker_once = subparsers.add_parser("worker-once", help="executa no máximo um trabalho persistido")
    worker_once.add_argument("--db", type=Path, required=True)
    worker_once.add_argument("--worker-id", required=True)
    worker_once.add_argument("--lease-seconds", type=float, default=30)

    verify_evidence = subparsers.add_parser("verify-evidence", help="verifica hashes dos artefatos de evidência")
    verify_evidence.add_argument("--db", type=Path, required=True)

    serve = subparsers.add_parser("serve", help="inicia a API local do SARE Operational")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--max-body-bytes", type=int, default=65_536)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "init-db":
        path = initialize_database(args.path)
        print(f"DATABASE_INITIALIZED {path}")
        return 0
    if args.command == "fetch-caixa":
        contest = fetch_caixa_contest(args.contest)
        persisted = persist_caixa_contest(args.db, contest)
        print(json.dumps({
            "contest_id": persisted.contest_id,
            "revision": persisted.revision,
            "created": persisted.created,
            "artifact_id": persisted.artifact_id,
            "source": contest.source_url,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "snapshot":
        snapshot = create_latest_snapshot(args.db)
        print(json.dumps(snapshot.__dict__ if hasattr(snapshot, "__dict__") else {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_hash": snapshot.snapshot_hash,
            "contest_count": snapshot.contest_count,
        }, sort_keys=True))
        return 0
    if args.command == "snapshot-as-of":
        try:
            cutoff = datetime.fromisoformat(args.availability_cutoff)
        except ValueError as exc:
            raise SystemExit(f"availability-cutoff inválido: {exc}") from exc
        if cutoff.tzinfo is None:
            raise SystemExit("availability-cutoff deve possuir timezone")
        snapshot = create_snapshot_as_of(args.db, cutoff)
        print(json.dumps({
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_hash": snapshot.snapshot_hash,
            "contest_count": snapshot.contest_count,
            "availability_cutoff": cutoff.isoformat(),
        }, sort_keys=True))
        return 0
    if args.command == "analyze-snapshot":
        report = analyze_core(load_snapshot_draws(args.db, args.snapshot), min_train=args.min_train)
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "validate-history":
        records = _load_legacy_file(args.path)
        if records is None:
            return 2
        print(json.dumps({"records": len(records), "first_contest": records[0].contest_id, "last_contest": records[-1].contest_id}, sort_keys=True))
        return 0
    if args.command == "analyze-history":
        records = _load_legacy_file(args.path)
        if records is None:
            return 2
        report = analyze_core(tuple(record.numbers for record in records), min_train=args.min_train)
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "backup-db":
        info = backup_database(args.db, args.out)
        print(json.dumps({"path": str(info.path), "sha256": info.sha256, "integrity": info.integrity}, sort_keys=True))
        return 0
    if args.command == "restore-db":
        info = restore_database(args.backup, args.out)
        print(json.dumps({"path": str(info.path), "sha256": info.sha256, "integrity": info.integrity}, sort_keys=True))
        return 0
    if args.command == "worker-once":
        job = run_worker_once(args.db, args.worker_id, lease_seconds=args.lease_seconds)
        if job is None:
            print("NO_JOB")
        else:
            print(json.dumps({"job_id": job.job_id, "state": job.state, "attempts": job.attempts}, sort_keys=True))
        return 0
    if args.command == "verify-evidence":
        checks = verify_source_artifacts(args.db)
        payload = {
            "valid": all(check.valid for check in checks),
            "artifacts": [
                {"artifact_id": c.artifact_id, "expected_sha256": c.expected_sha256, "actual_sha256": c.actual_sha256, "valid": c.valid, "error": c.error}
                for c in checks
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload["valid"] else 3
    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit("Operational 1.1 recusa binding externo; use loopback local")
        from sare_lotofacil.api.app import create_app
        import uvicorn

        app = create_app(
            args.db,
            write_token=os.getenv("SARE_WRITE_TOKEN"),
            max_body_bytes=args.max_body_bytes,
        )
        uvicorn.run(app, host=args.host, port=args.port)
        return 0
    raise RuntimeError("comando não tratado")
