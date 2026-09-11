from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_null_simulator_is_reproducible_and_valid() -> None:
    first = simulate_uniform_draws(100, seed=123)
    second = simulate_uniform_draws(100, seed=123)
    assert first == second
    assert all(len(draw) == 15 and len(set(draw)) == 15 for draw in first.draws)
    assert all(1 <= min(draw) and max(draw) <= 25 for draw in first.draws)


def test_null_simulator_does_not_forbid_repeated_full_draws() -> None:
    simulation = simulate_uniform_draws(3, seed=7)
    assert len(simulation.draws) == 3
