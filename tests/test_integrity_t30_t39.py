from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from sare_lotofacil.api.app import create_app
from sare_lotofacil.economics import calculate_economic_audit, summarize_horizon_cashflow
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import connect
from sare_lotofacil.persistence.operations import persist_uniform_portfolio
from sare_lotofacil.persistence.repository import persist_caixa_contest
from sare_lotofacil.portfolios.core import generate_uniform_portfolio, normalize_portfolio_cards
from sare_lotofacil.portfolios.coverage import exact_jackpot_coverage
from sare_lotofacil.portfolios.search import PortfolioSearchPolicy, search_bounded_portfolio


def test_t30_operational_card_count_outside_1_100_is_rejected() -> None:
    single = generate_uniform_portfolio(1, seed=1)
    assert len(single.cards) == 1
    with pytest.raises(ValueError, match="1 e 100"):
        generate_uniform_portfolio(0, seed=1)
    with pytest.raises(ValueError, match="1 e 100"):
        generate_uniform_portfolio(101, seed=1)


def test_t31_duplicate_card_is_rejected_without_silent_count_reduction() -> None:
    card = tuple(range(1, 16))
    with pytest.raises(ValueError, match="DUPLICATE_CARD"):
        normalize_portfolio_cards((card, card), expected_count=2)

    portfolio = generate_uniform_portfolio(10, seed=20260914)
    assert len(portfolio.cards) == 10
    assert len(set(portfolio.cards)) == 10


def test_t32_exhausted_bounded_search_reports_limit_not_proven_infeasibility() -> None:
    policy = PortfolioSearchPolicy(max_overlap=0, max_exposure=1.0, max_attempts=12, seed=7)
    result = search_bounded_portfolio(3, policy=policy)

    assert result.status == "SEARCH_LIMIT_REACHED"
    assert result.attempts == 12
    assert result.cards == ()
    assert "INFEASIBLE" not in result.status


def test_t33_relaxed_constraint_requires_new_identified_configuration() -> None:
    strict = PortfolioSearchPolicy(max_overlap=9, max_exposure=0.75, max_attempts=100, seed=7)
    relaxed = PortfolioSearchPolicy(max_overlap=10, max_exposure=0.75, max_attempts=100, seed=7)

    assert strict.config_id != relaxed.config_id
    assert strict.config_hash != relaxed.config_hash


def test_t34_distinct_cards_have_exact_jackpot_coverage_m_over_space() -> None:
    portfolio = generate_uniform_portfolio(5, seed=34)
    coverage = exact_jackpot_coverage(portfolio.cards)

    assert coverage.card_count == 5
    assert coverage.covered_outcomes == 5
    assert coverage.total_outcomes == 3_268_760
    assert coverage.probability == 5 / 3_268_760


def test_t35_unpurchased_portfolio_does_not_create_real_expense() -> None:
    audit = calculate_economic_audit(
        [11, 10, 9],
        {15: 1_000_000, 14: 50_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
    )

    assert audit.purchase_recorded is False
    assert audit.actual_cost_cents is None
    assert audit.actual_net_cents is None
    assert audit.theoretical_cost_cents == 1_050


def test_t36_each_prize_tier_keeps_its_own_value_and_source() -> None:
    sources = {
        15: "caixa://contest-500/revision-1/tier-15",
        14: "caixa://contest-500/revision-1/tier-14",
        13: "caixa://contest-500/revision-1/tier-13",
        12: "caixa://contest-500/revision-1/tier-12",
        11: "caixa://contest-500/revision-1/tier-11",
    }
    audit = calculate_economic_audit(
        [15, 14],
        {15: 80_000_000, 14: 125_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=700,
        rateio_source_by_hits=sources,
        round_id="contest-500/revision-1",
    )

    assert audit.prize_by_card_cents == (80_000_000, 125_000)
    source_map = dict(audit.rateio_source_by_tier)
    assert source_map[15] != source_map[14]
    assert source_map[15].endswith("tier-15")
    assert source_map[14].endswith("tier-14")


def test_t37_same_tier_wins_share_same_per_unit_rateio_in_round() -> None:
    audit = calculate_economic_audit(
        [14, 14, 15],
        {15: 50_000_000, 14: 98_765, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
        round_id="contest-501/revision-1",
    )

    assert audit.prize_by_card_cents[0] == audit.prize_by_card_cents[1] == 98_765
    assert audit.prize_by_card_cents[2] == 50_000_000


def test_t38_single_contest_and_long_horizon_preserve_different_loss_interpretation() -> None:
    one = summarize_horizon_cashflow(1_000, [-300], next_participation_cost_cents=300)
    prolonged = summarize_horizon_cashflow(1_000, [-300, -300, -300, -300], next_participation_cost_cents=300)

    assert one.horizon_contests == 1
    assert one.net_loss_cents == 300
    assert one.cannot_fund_next_participation is False
    assert prolonged.horizon_contests == 4
    assert prolonged.net_loss_cents == 1_200
    assert prolonged.cannot_fund_next_participation is True


def test_t39_same_portfolio_and_contest_revision_audit_is_idempotent(tmp_path) -> None:
    db = tmp_path / "sare.db"
    portfolio = persist_uniform_portfolio(db, card_count=3, seed=39, target_contest=500)
    contest = CaixaContest(
        record=validate_contest(500, date(2026, 9, 14), range(1, 16)),
        prize_tiers=(),
        source_url="fixture://contest/500/revision/1",
        captured_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        raw_payload={"numero": 500, "listaDezenas": list(range(1, 16))},
    )
    persisted = persist_caixa_contest(db, contest, source_class="SINTETICO")
    assert persisted.revision == 1

    client = TestClient(create_app(db, write_token="secret"))
    body = {"portfolio_id": portfolio.portfolio_id, "contest_id": 500, "revision": 1}
    first = client.post(
        "/v1/evaluations/revisions",
        json=body,
        headers={"Idempotency-Key": "rev-eval-1", "X-SARE-Token": "secret"},
    )
    second = client.post(
        "/v1/evaluations/revisions",
        json=body,
        headers={"Idempotency-Key": "rev-eval-2", "X-SARE-Token": "secret"},
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["contest_id"] == 500
    assert first.json()["revision"] == 1
    assert first.json()["evaluation_class"] == "CANONICAL_EVALUATION"
    assert first.json()["evidence_eligible"] is True
    assert first.json()["source_class"] == "SINTETICO"

    with connect(db) as connection:
        evaluations = connection.execute("SELECT COUNT(*) FROM revision_evaluations").fetchone()[0]
        audit_events = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action='PORTFOLIO_CANONICAL_EVALUATED'"
        ).fetchone()[0]
    assert evaluations == 1
    assert audit_events == 1
