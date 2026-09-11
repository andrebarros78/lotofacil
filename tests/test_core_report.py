from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_core_report_never_promotes_retrospective_result() -> None:
    draws = simulate_uniform_draws(300, seed=1234).draws
    report = analyze_core(draws)
    assert report.contest_count == 300
    assert report.min_train == 180
    assert report.predictive_evidence == "NOT_ESTABLISHED"
    assert report.scientific_conclusion == "EVIDENCIA_PREDITIVA_INSUFICIENTE"
    assert report.m1_frequency.predictions == 120
    assert report.m2_exponential.predictions == 120
