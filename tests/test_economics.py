import pytest

from sare_lotofacil.economics import calculate_economic_audit


def test_economic_audit_uses_rateio_per_card_and_keeps_purchase_unrecorded():
    audit = calculate_economic_audit(
        [15, 14, 13, 10, 11],
        {15: 500_000_00, 14: 1_000_00, 13: 35_00, 12: 14_00, 11: 7_00},
        theoretical_cost_cents=15_00,
    )
    assert audit.prize_by_card_cents == (500_000_00, 1_000_00, 35_00, 0, 7_00)
    assert audit.prize_total_cents == 501_042_00
    assert audit.hypothetical_net_cents == 501_027_00
    assert audit.purchase_recorded is False
    assert audit.actual_cost_cents is None
    assert audit.actual_net_cents is None
    assert dict(audit.prize_count_by_tier) == {15: 1, 14: 1, 13: 1, 12: 0, 11: 1}


def test_economic_audit_requires_complete_rateio():
    with pytest.raises(ValueError, match="exatamente as faixas"):
        calculate_economic_audit([11], {11: 700}, theoretical_cost_cents=300)


def test_economic_audit_rejects_negative_prize():
    with pytest.raises(ValueError, match="prêmio negativo"):
        calculate_economic_audit(
            [11],
            {15: 0, 14: 0, 13: 0, 12: 0, 11: -1},
            theoretical_cost_cents=300,
        )
