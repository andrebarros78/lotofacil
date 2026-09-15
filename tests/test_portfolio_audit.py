from __future__ import annotations

from sare_lotofacil.analysis.portfolio_audit import run_primary_tiebreak_audit
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_primary_tiebreak_audit_is_reproducible_and_never_promotes_evidence() -> None:
    draws = simulate_uniform_draws(360, seed=2026091522).draws
    first = run_primary_tiebreak_audit(draws, evaluation_start=288)
    second = run_primary_tiebreak_audit(draws, evaluation_start=288)
    assert first == second
    assert first["evaluation_windows"] == 72
    assert first["windows_with_boundary_tie"] >= 0
    assert first["bootstrap_replications"] == 2000
    assert first["predictive_evidence"] == "NOT_ESTABLISHED"
    assert first["scientific_conclusion"] in {
        "M2_TIEBREAK_RETROSPECTIVE_POSITIVE_SIGNAL",
        "M2_TIEBREAK_RETROSPECTIVE_NEGATIVE_SIGNAL",
        "M2_TIEBREAK_NO_DEMONSTRATED_INCREMENTAL_VALUE",
    }
