import pytest

from sare_lotofacil.domain.rules import (
    INDEPENDENCIA_2026_RULESET,
    special_prize_ruleset_for_contest,
)


def test_contest_3780_uses_explicit_independencia_2026_ruleset():
    rules = special_prize_ruleset_for_contest(3780)
    assert rules is INDEPENDENCIA_2026_RULESET
    assert rules.fixed_prize_cents(11) == 350
    assert rules.fixed_prize_cents(12) == 700
    assert rules.fixed_prize_cents(13) == 1750
    assert rules.variable_share_bps(14) == 1300
    assert rules.variable_share_bps(15) == 8700
    assert rules.non_accumulating is True
    assert rules.source_url.startswith("https://www.caixa.gov.br/")


def test_special_rules_are_not_silently_applied_to_regular_contest():
    assert special_prize_ruleset_for_contest(3779) is None
    assert special_prize_ruleset_for_contest(3781) is None


def test_special_ruleset_lookup_rejects_invalid_contest_id():
    with pytest.raises(ValueError, match="inteiro positivo"):
        special_prize_ruleset_for_contest(0)
