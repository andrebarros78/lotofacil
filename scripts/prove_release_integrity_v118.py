from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.economics import calculate_economic_audit, summarize_horizon_cashflow
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect
from sare_lotofacil.persistence.operations import evaluate_portfolio_revision, persist_uniform_portfolio
from sare_lotofacil.persistence.repository import persist_caixa_contest
from sare_lotofacil.portfolios.core import generate_uniform_portfolio, normalize_portfolio_cards
from sare_lotofacil.portfolios.coverage import exact_jackpot_coverage
from sare_lotofacil.portfolios.search import PortfolioSearchPolicy, search_bounded_portfolio

try:
    import prove_release_integrity as legacy
except ModuleNotFoundError:
    from scripts import prove_release_integrity as legacy


def prove_portfolio_economics_v118() -> None:
    single = generate_uniform_portfolio(1, seed=1)
    assert len(single.cards) == 1 and single.cost_cents == 350

    blocked_counts: list[int] = []
    for count in (0, 101):
        try:
            generate_uniform_portfolio(count, seed=1)
        except ValueError:
            blocked_counts.append(count)
    assert blocked_counts == [0, 101]

    card = tuple(range(1, 16))
    duplicate_blocked = False
    try:
        normalize_portfolio_cards((card, card), expected_count=2)
    except ValueError as exc:
        duplicate_blocked = "DUPLICATE_CARD" in str(exc)
    assert duplicate_blocked

    generated = generate_uniform_portfolio(10, seed=20260914)
    assert len(generated.cards) == len(set(generated.cards)) == 10

    strict = PortfolioSearchPolicy(max_overlap=0, max_exposure=1.0, max_attempts=12, seed=7)
    bounded = search_bounded_portfolio(3, policy=strict)
    assert bounded.status == "SEARCH_LIMIT_REACHED"
    assert bounded.attempts == 12 and bounded.cards == ()
    assert "INFEASIBLE" not in bounded.status

    relaxed = PortfolioSearchPolicy(max_overlap=10, max_exposure=1.0, max_attempts=12, seed=7)
    assert strict.config_id != relaxed.config_id
    assert strict.config_hash != relaxed.config_hash

    jackpot = exact_jackpot_coverage(generate_uniform_portfolio(5, seed=34).cards)
    assert jackpot.covered_outcomes == 5
    assert jackpot.total_outcomes == 3_268_760
    assert jackpot.probability == 5 / 3_268_760

    unpurchased = calculate_economic_audit(
        [11, 10, 9],
        {15: 1_000_000, 14: 50_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
    )
    assert unpurchased.purchase_recorded is False
    assert unpurchased.actual_cost_cents is None
    assert unpurchased.actual_net_cents is None

    sources = {tier: f"caixa://contest-500/revision-1/tier-{tier}" for tier in (15, 14, 13, 12, 11)}
    tiered = calculate_economic_audit(
        [15, 14],
        {15: 80_000_000, 14: 125_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=700,
        rateio_source_by_hits=sources,
        round_id="contest-500/revision-1",
    )
    assert tiered.prize_by_card_cents == (80_000_000, 125_000)
    assert dict(tiered.rateio_source_by_tier)[15] != dict(tiered.rateio_source_by_tier)[14]

    same_tier = calculate_economic_audit(
        [14, 14, 15],
        {15: 50_000_000, 14: 98_765, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
        round_id="contest-501/revision-1",
    )
    assert same_tier.prize_by_card_cents[0] == same_tier.prize_by_card_cents[1] == 98_765

    one = summarize_horizon_cashflow(1_000, [-300], next_participation_cost_cents=300)
    prolonged = summarize_horizon_cashflow(1_000, [-300, -300, -300, -300], next_participation_cost_cents=300)
    assert one.horizon_contests == 1 and one.net_loss_cents == 300
    assert prolonged.horizon_contests == 4 and prolonged.net_loss_cents == 1_200
    assert one.cannot_fund_next_participation is False
    assert prolonged.cannot_fund_next_participation is True

    db = Path("/tmp/t30-t39-release-v118.db")
    db.unlink(missing_ok=True)
    portfolio = persist_uniform_portfolio(db, card_count=1, seed=39, target_contest=500)
    assert len(portfolio.cards) == 1
    contest = CaixaContest(
        record=validate_contest(500, date(2026, 9, 14), range(1, 16)),
        prize_tiers=(),
        source_url="fixture://contest/500/revision/1",
        captured_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        raw_payload={"numero": 500, "listaDezenas": list(range(1, 16))},
    )
    persisted = persist_caixa_contest(db, contest, source_class="SINTETICO")
    assert persisted.revision == 1
    first = evaluate_portfolio_revision(db, portfolio.portfolio_id, 500, 1)
    second = evaluate_portfolio_revision(db, portfolio.portfolio_id, 500, 1)
    assert first == second

    with connect(db) as connection:
        revision_rows = connection.execute("SELECT COUNT(*) FROM revision_evaluations").fetchone()[0]
        audit_rows = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action='PORTFOLIO_CANONICAL_EVALUATED'"
        ).fetchone()[0]
        schema_version = int(
            connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
        )
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert revision_rows == 1
    assert audit_rows == 1
    assert schema_version == SCHEMA_VERSION == 7
    assert foreign_key_violations == []

    payload = {
        "status": "PORTFOLIO_ECONOMIC_INTEGRITY_RELEASE_PROOF_PASS",
        "t30_single_card_allowed": True,
        "t30_blocked_counts": blocked_counts,
        "t31_duplicate_blocked": duplicate_blocked,
        "t31_delivered_count": len(generated.cards),
        "t32": asdict(bounded),
        "t33_strict_policy_id": strict.config_id,
        "t33_relaxed_policy_id": relaxed.config_id,
        "t34": asdict(jackpot),
        "t35": {
            "purchase_recorded": unpurchased.purchase_recorded,
            "actual_cost_cents": unpurchased.actual_cost_cents,
            "actual_net_cents": unpurchased.actual_net_cents,
            "theoretical_cost_cents": unpurchased.theoretical_cost_cents,
        },
        "t36": {
            "prize_by_card_cents": tiered.prize_by_card_cents,
            "rateio_source_by_tier": tiered.rateio_source_by_tier,
            "round_id": tiered.round_id,
        },
        "t37_prize_by_card_cents": same_tier.prize_by_card_cents,
        "t38_one": asdict(one),
        "t38_prolonged": asdict(prolonged),
        "t39": {
            "evaluation_id": first.evaluation_id,
            "contest_id": first.contest_id,
            "revision": first.revision,
            "revision_rows": revision_rows,
            "audit_rows": audit_rows,
            "schema_version": schema_version,
            "foreign_key_violations": foreign_key_violations,
        },
    }
    legacy._write("portfolio_economic_integrity_release_proof.json", payload)
    print(payload["status"])


def main() -> int:
    legacy.prove_regime()
    legacy.prove_controlled_alternatives()
    legacy.prove_backtest()
    legacy.prove_risk_repro_coverage()
    prove_portfolio_economics_v118()
    legacy.prove_primary_card()
    print("RELEASE_INTEGRITY_SUITE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
