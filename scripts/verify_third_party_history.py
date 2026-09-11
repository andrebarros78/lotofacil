from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.ingestion.csv_history import parse_history_csv
from sare_lotofacil.persistence.backup import database_integrity
from sare_lotofacil.persistence.repository import (
    create_latest_snapshot,
    load_snapshot_records,
    persist_caixa_contest,
    persist_history_records,
)
from sare_lotofacil.statistics.inference import marginal_tests, pair_tests, temporal_repetition_monte_carlo

SOURCE_URL = "https://raw.githubusercontent.com/heldersontuc-collab/lotofacil-data/main/data/lotofacil.csv"
CHECKPOINTS = (1, 100, 949, 2000, 3000, 3766)
MAX_OFFICIAL_PATCHES = 20


def download_text(url: str) -> bytes:
    request = Request(url, headers={"Accept": "text/csv", "User-Agent": "SARE-Lotofacil/0.2"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _record_identity(record) -> tuple[int, str, tuple[int, ...]]:
    return record.contest_id, record.draw_date.isoformat(), record.numbers


def main() -> int:
    raw = download_text(SOURCE_URL)
    captured_at = datetime.now(timezone.utc)
    digest = hashlib.sha256(raw).hexdigest()
    parsed = parse_history_csv(raw.decode("utf-8-sig"))

    non_gap_issues = [issue for issue in parsed.issues if not issue.message.startswith("lacuna de concursos")]
    if non_gap_issues:
        print(json.dumps({"status": "INVALID_SOURCE", "issues": [asdict(issue) for issue in non_gap_issues[:50]]}, ensure_ascii=False))
        return 2
    if not parsed.records or parsed.records[0].contest_id != 1:
        raise RuntimeError("histórico não inicia no concurso 1")

    official_latest = fetch_caixa_contest()
    source_last_contest = parsed.records[-1].contest_id
    if source_last_contest != official_latest.record.contest_id:
        print(json.dumps({
            "status": "STALE_SOURCE",
            "candidate_last_contest": source_last_contest,
            "official_last_contest": official_latest.record.contest_id,
        }, ensure_ascii=False, sort_keys=True))
        return 4

    by_id = {record.contest_id: record for record in parsed.records}
    missing_ids = [contest_id for contest_id in range(1, source_last_contest + 1) if contest_id not in by_id]
    if len(missing_ids) > MAX_OFFICIAL_PATCHES:
        print(json.dumps({
            "status": "TOO_MANY_SOURCE_GAPS",
            "missing_count": len(missing_ids),
            "missing_contests": missing_ids[:100],
        }, ensure_ascii=False, sort_keys=True))
        return 5

    official_cache = {official_latest.record.contest_id: official_latest}
    official_patches = []
    for contest_id in missing_ids:
        official = fetch_caixa_contest(contest_id)
        official_cache[contest_id] = official
        by_id[contest_id] = official.record
        official_patches.append({
            "contest_id": contest_id,
            "source_url": official.source_url,
            "draw_date": official.record.draw_date.isoformat(),
        })

    records = tuple(by_id[contest_id] for contest_id in range(1, source_last_contest + 1))
    checkpoint_ids = tuple(dict.fromkeys((*CHECKPOINTS, records[-1].contest_id)))
    checks = []
    for contest_id in checkpoint_ids:
        official = official_cache.get(contest_id) or fetch_caixa_contest(contest_id)
        official_cache[contest_id] = official
        candidate = by_id[contest_id]
        matches = candidate.draw_date == official.record.draw_date and candidate.numbers == official.record.numbers
        checks.append({
            "contest_id": contest_id,
            "matches_official": matches,
            "candidate_date": candidate.draw_date.isoformat(),
            "official_date": official.record.draw_date.isoformat(),
            "candidate_origin": "OFICIAL_DIRETA_PATCH" if contest_id in missing_ids else "TERCEIRO_CORROBORADO",
        })
        if not matches:
            print(json.dumps({"status": "CHECKPOINT_MISMATCH", "checkpoint": checks[-1]}, ensure_ascii=False))
            return 3

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    db_path = artifacts_dir / "real_history.db"
    db_path.unlink(missing_ok=True)

    bulk = persist_history_records(
        db_path,
        parsed.records,
        source_url=SOURCE_URL,
        raw_bytes=raw,
        captured_at=captured_at,
        source_class="TERCEIRO_CORROBORADO",
    )
    if bulk.source_sha256 != digest:
        raise RuntimeError("hash do artefato persistido divergiu da captura")
    for contest_id in missing_ids:
        persist_caixa_contest(db_path, official_cache[contest_id], source_class="OFICIAL_DIRETA")

    snapshot = create_latest_snapshot(db_path)
    reloaded = load_snapshot_records(db_path, snapshot.snapshot_id)
    expected_identity = tuple(_record_identity(record) for record in records)
    reloaded_identity = tuple(_record_identity(record) for record in reloaded)
    if reloaded_identity != expected_identity:
        raise RuntimeError("snapshot recarregado divergiu do histórico reconciliado")
    integrity = database_integrity(db_path)
    if integrity != "ok":
        raise RuntimeError(f"integrity_check falhou: {integrity}")

    draws = tuple(record.numbers for record in reloaded)
    report = analyze_core(draws)
    marginal = marginal_tests(draws)
    pairs = pair_tests(draws)
    temporal = temporal_repetition_monte_carlo(draws, replications=999, seed=20260911)

    result = {
        "status": "THIRD_PARTY_CORROBORATED_WITH_OFFICIAL_PATCHES",
        "source_class": "TERCEIRO_CORROBORADO",
        "source_url": SOURCE_URL,
        "source_sha256": digest,
        "source_artifact_id": bulk.artifact_id,
        "source_records": len(parsed.records),
        "records_after_official_patches": len(records),
        "first_contest": records[0].contest_id,
        "last_contest": records[-1].contest_id,
        "official_latest_contest": official_latest.record.contest_id,
        "official_patches": official_patches,
        "checkpoints": checks,
        "persistence_verified": True,
        "persistence_inserted_third_party": bulk.inserted,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "snapshot_contest_count": snapshot.contest_count,
        "snapshot_roundtrip_exact": True,
        "database_integrity": integrity,
        "core_report": report.to_dict(),
        "marginal_min_holm": min(item.p_holm for item in marginal),
        "marginal_max_abs_effect": max(abs(item.effect) for item in marginal),
        "pair_min_holm": min(item.p_holm for item in pairs),
        "pair_max_abs_effect": max(abs(item.effect) for item in pairs),
        "temporal_repetition": asdict(temporal),
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
        "limitations": [
            "A maior parte da série histórica vem de terceiro e foi corroborada por checkpoints contra a CAIXA, não reconciliada linha a linha.",
            "Lacunas do terceiro foram preenchidas individualmente por OFICIAL_DIRETA e permanecem listadas em official_patches.",
            "A análise é retrospectiva e não constitui prova prospectiva.",
            "Monte Carlo temporal usa 999 replicações nesta verificação, com resolução mínima 0,001.",
        ],
    }
    out = artifacts_dir / "third_party_history_report.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
