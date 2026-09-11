from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest


@dataclass(frozen=True, slots=True)
class ImportIssue:
    line_number: int
    message: str
    raw_line: str


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    records: tuple[ContestRecord, ...]
    issues: tuple[ImportIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        raise ValueError("linha não é uma linha de tabela Markdown")
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def parse_legacy_markdown(text: str) -> LegacyImportResult:
    lines = text.splitlines()
    header_index: int | None = None
    header: list[str] | None = None
    for index, line in enumerate(lines):
        if "| Concurso |" in line and "Data Sorteio" in line and "Bola15" in line:
            header_index = index
            header = _split_markdown_row(line)
            break
    if header_index is None or header is None:
        return LegacyImportResult((), (ImportIssue(0, "cabeçalho LOTOFÁCIL não encontrado", ""),))

    required = ["Concurso", "Data Sorteio", *[f"Bola{i}" for i in range(1, 16)]]
    missing = [column for column in required if column not in header]
    if missing:
        return LegacyImportResult((), (ImportIssue(header_index + 1, f"colunas obrigatórias ausentes: {', '.join(missing)}", lines[header_index]),))
    positions = {column: header.index(column) for column in required}

    records: list[ContestRecord] = []
    issues: list[ImportIssue] = []
    seen_ids: set[int] = set()
    for zero_index, line in enumerate(lines[header_index + 2 :], start=header_index + 2):
        if not line.strip().startswith("|"):
            if records:
                break
            continue
        try:
            cells = _split_markdown_row(line)
            if len(cells) != len(header):
                raise ValueError(f"quantidade de colunas divergente: esperadas {len(header)}, recebidas {len(cells)}")
            contest_id = int(cells[positions["Concurso"]])
            if contest_id in seen_ids:
                raise ValueError(f"concurso duplicado: {contest_id}")
            draw_date = datetime.strptime(cells[positions["Data Sorteio"]], "%d/%m/%Y").date()
            numbers = tuple(int(cells[positions[f"Bola{i}"]]) for i in range(1, 16))
            record = validate_contest(contest_id, draw_date, numbers)
            seen_ids.add(contest_id)
            records.append(record)
        except Exception as exc:
            issues.append(ImportIssue(zero_index + 1, str(exc), line))

    ordered = tuple(sorted(records, key=lambda record: record.contest_id))
    for previous, current in zip(ordered, ordered[1:]):
        if current.contest_id != previous.contest_id + 1:
            issues.append(ImportIssue(0, f"lacuna de concursos entre {previous.contest_id} e {current.contest_id}", ""))
        if current.draw_date < previous.draw_date:
            issues.append(ImportIssue(0, f"data regressiva entre concursos {previous.contest_id} e {current.contest_id}", ""))
    return LegacyImportResult(ordered, tuple(issues))
