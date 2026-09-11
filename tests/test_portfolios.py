from sare_lotofacil.portfolios.core import UNPROVEN_LABEL, audit_portfolio, generate_uniform_portfolio


def test_portfolio_is_unique_reproducible_and_labeled() -> None:
    first = generate_uniform_portfolio(10, seed=77)
    second = generate_uniform_portfolio(10, seed=77)
    assert first == second
    assert len(first.cards) == len(set(first.cards)) == 10
    assert first.cost_cents == 3500
    assert first.evidence_label == UNPROVEN_LABEL


def test_portfolio_audit_counts_hits() -> None:
    portfolio = generate_uniform_portfolio(3, seed=2)
    hits = audit_portfolio(portfolio, range(1, 16))
    assert len(hits) == 3
    assert all(5 <= value <= 15 for value in hits)
