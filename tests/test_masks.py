import pytest

from sare_lotofacil.domain.masks import intersection_hits, mask_to_numbers, numbers_to_mask


CARD = tuple(range(1, 16))


def test_mask_roundtrip() -> None:
    mask = numbers_to_mask(CARD)
    assert mask_to_numbers(mask) == CARD


def test_intersection_hits() -> None:
    left = numbers_to_mask(range(1, 16))
    right = numbers_to_mask(range(11, 26))
    assert intersection_hits(left, right) == 5


@pytest.mark.parametrize(
    "numbers",
    [
        list(range(1, 15)),
        list(range(1, 15)) + [14],
        list(range(1, 15)) + [26],
    ],
)
def test_invalid_cards_are_rejected(numbers: list[int]) -> None:
    with pytest.raises(ValueError):
        numbers_to_mask(numbers)
