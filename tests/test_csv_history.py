from sare_lotofacil.ingestion.csv_history import parse_history_csv


def test_csv_history_parser_accepts_canonical_contract() -> None:
    header = "concurso,data," + ",".join(f"d{i}" for i in range(1, 16))
    row1 = "1,29/09/2003," + ",".join(f"{n:02d}" for n in [2,3,5,6,9,10,11,13,14,16,18,20,23,24,25])
    row2 = "2,2003-10-06," + ",".join(f"{n:02d}" for n in [1,4,5,6,7,9,11,12,13,15,16,19,20,23,24])
    result = parse_history_csv("\n".join([header, row1, row2]))
    assert result.is_valid
    assert [record.contest_id for record in result.records] == [1, 2]


def test_csv_history_parser_reports_gap() -> None:
    header = "concurso,data," + ",".join(f"d{i}" for i in range(1, 16))
    numbers = ",".join(str(n) for n in range(1, 16))
    result = parse_history_csv(f"{header}\n1,01/01/2026,{numbers}\n3,03/01/2026,{numbers}\n")
    assert not result.is_valid
    assert any("lacuna" in issue.message for issue in result.issues)
