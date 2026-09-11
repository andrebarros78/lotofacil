from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from sare_lotofacil.ingestion.legacy_markdown import ImportIssue
from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest


@dataclass(frozen=True, slots=True)
class CsvImportResult:
    records: tuple[ContestRecord, ...]
    issues: tuple[ImportIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _parse_date(value: str):
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"data inválida: {value!r}")


def parse_history_csv(text: str) -> CsvImportResult:
    stream = io.StringIO(text.lstrip("\ufeff"))
    reader = csv.DictReader(stream)
    expected = ["concurso", "data", *[f"d{i}" for i in range(1, 16)]]
    if reader.fieldnames is None:
        return CsvImportResult((), (ImportIssue(1, "CSV sem cabeçalho", ""),))
    missing = [column for column in expected if column not in reader.fieldnames]
    if missing:
        return CsvImportResult((), (ImportIssue(1, f"colunas obrigatórias ausentes: {', '.join(missing)}", ",".join(reader.fieldnames)),))

    records: list[ContestRecord] = []
    issues: list[ImportIssue] = []
    seen: set[int] = set()
    for line_number, row in enumerate(reader, start=2):
        try:
            contest_id = int((row.get("concurso") or "").strip())
            if contest_id in seen:
                raise ValueError(f"concurso duplicado: {contest_id}")
            draw_date = _parse_date(row.get("data") or "")
            numbers = tuple(int((row.get(f"d{i}") or "").strip()) for i in range(1, 16))
            record = validate_contest(contest_id, draw_date, numbers)
            seen.add(contest_id)
            records.append(record)
        except Exception as exc:
            issues.append(ImportIssue(line_number, str(exc), str(row)))

    ordered = tuple(sorted(records, key=lambda record: record.contest_id))
    for previous, current in zip(ordered, ordered[1:]):
        if current.contest_id != previous.contest_id + 1:
            issues.append(ImportIssue(0, f"lacuna de concursos entre {previous.contest_id} e {current.contest_id}", ""))
        if current.draw_date < previous.draw_date:
            issues.append(ImportIssue(0, f"data regressiva entre concursos {previous.contest_id} e {current.contest_id}", ""))
    return CsvImportResult(ordered, tuple(issues))
