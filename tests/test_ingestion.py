from datetime import date

import pytest

from sare_lotofacil.ingestion.validation import validate_contest


def test_valid_contest_is_normalized() -> None:
    record = validate_contest(1, date(2003, 9, 29), reversed(range(1, 16)))
    assert record.numbers == tuple(range(1, 16))
    assert record.mask.bit_count() == 15


@pytest.mark.parametrize("contest_id", [0, -1, True, 1.5])
def test_invalid_contest_id_is_rejected(contest_id) -> None:
    with pytest.raises(ValueError):
        validate_contest(contest_id, date(2003, 9, 29), range(1, 16))
