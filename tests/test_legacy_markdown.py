from sare_lotofacil.ingestion.legacy_markdown import parse_legacy_markdown


HEADER = "| Concurso | Data Sorteio | " + " | ".join(f"Bola{i}" for i in range(1, 16)) + " | Extra |\n"
DIVIDER = "| " + " | ".join(["---"] * 18) + " |\n"


def row(contest: int, date: str, numbers=range(1, 16)) -> str:
    values = [str(contest), date, *[str(number) for number in numbers], "x"]
    return "| " + " | ".join(values) + " |\n"


def test_legacy_import_validates_and_orders() -> None:
    text = "# Lotofácil\n\n" + HEADER + DIVIDER + row(1, "01/01/2026") + row(2, "02/01/2026", range(11, 26))
    result = parse_legacy_markdown(text)
    assert result.is_valid
    assert [record.contest_id for record in result.records] == [1, 2]
    assert result.records[0].mask.bit_count() == 15


def test_legacy_import_reports_bad_row_and_gap() -> None:
    bad_numbers = list(range(1, 15)) + [14]
    text = HEADER + DIVIDER + row(1, "01/01/2026") + row(2, "02/01/2026", bad_numbers) + row(3, "03/01/2026", range(11, 26))
    result = parse_legacy_markdown(text)
    assert not result.is_valid
    messages = [issue.message for issue in result.issues]
    assert any("repetidas" in message for message in messages)
    assert any("lacuna" in message for message in messages)
