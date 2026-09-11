from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.ingestion.csv_history import parse_history_csv
from sare_lotofacil.statistics.inference import marginal_tests, pair_tests, temporal_repetition_monte_carlo

SOURCE_URL = "https://raw.githubusercontent.com/heldersontuc-collab/lotofacil-data/main/data/lotofacil.csv"
CHECKPOINTS = (1, 100, 949, 2000, 3000, 3766)


def download_text(url: str) -> bytes:
    request = Request(url, headers={"Accept": "text/csv", "User-Agent": "SARE-Lotofacil/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def main() -> int:
    raw = download_text(SOURCE_URL)
    digest = hashlib.sha256(raw).hexdigest()
    parsed = parse_history_csv(raw.decode("utf-8-sig"))
    if not parsed.is_valid:
        print(json.dumps({"status": "INVALID_SOURCE", "issues": [asdict(issue) for issue in parsed.issues[:50]]}, ensure_ascii=False))
        return 2
    records = parsed.records
    if not records or records[0].contest_id != 1:
        raise RuntimeError("histórico não inicia no concurso 1")

    by_id = {record.contest_id: record for record in records}
    checkpoint_ids = tuple(dict.fromkeys((*CHECKPOINTS, records[-1].contest_id)))
    checks = []
    for contest_id in checkpoint_ids:
        if contest_id not in by_id:
            raise RuntimeError(f"checkpoint ausente no CSV: {contest_id}")
        official = fetch_caixa_contest(contest_id)
        candidate = by_id[contest_id]
        matches = candidate.draw_date == official.record.draw_date and candidate.numbers == official.record.numbers
        checks.append({
            "contest_id": contest_id,
            "matches_official": matches,
            "candidate_date": candidate.draw_date.isoformat(),
            "official_date": official.record.draw_date.isoformat(),
        })
        if not matches:
            print(json.dumps({"status": "CHECKPOINT_MISMATCH", "checkpoint": checks[-1]}, ensure_ascii=False))
            return 3

    draws = tuple(record.numbers for record in records)
    report = analyze_core(draws)
    marginal = marginal_tests(draws)
    pairs = pair_tests(draws)
    temporal = temporal_repetition_monte_carlo(draws, replications=999, seed=20260911)

    result = {
        "status": "THIRD_PARTY_CORROBORATED_CHECKPOINTS",
        "source_class": "TERCEIRO_CORROBORADO",
        "source_url": SOURCE_URL,
        "source_sha256": digest,
        "records": len(records),
        "first_contest": records[0].contest_id,
        "last_contest": records[-1].contest_id,
        "checkpoints": checks,
        "core_report": report.to_dict(),
        "marginal_min_holm": min(item.p_holm for item in marginal),
        "marginal_max_abs_effect": max(abs(item.effect) for item in marginal),
        "pair_min_holm": min(item.p_holm for item in pairs),
        "pair_max_abs_effect": max(abs(item.effect) for item in pairs),
        "temporal_repetition": asdict(temporal),
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
        "limitations": [
            "A fonte histórica completa é de terceiro e foi apenas corroborada por checkpoints contra a CAIXA.",
            "A análise é retrospectiva e não constitui prova prospectiva.",
            "Monte Carlo temporal usa 999 replicações nesta verificação, com resolução mínima 0,001.",
        ],
    }
    out = Path("artifacts/third_party_history_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
