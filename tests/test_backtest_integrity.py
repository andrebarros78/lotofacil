from __future__ import annotations

import pytest

from sare_lotofacil.experiments.backtest import (
    BacktestLeakageError,
    BacktestWindow,
    FittedTransform,
    TemporalVariable,
    run_audited_backtest,
)


def _window(index: int) -> BacktestWindow:
    training_last = 100 + index
    return BacktestWindow(
        window_id=f"window-{index:02d}",
        training_last_contest=training_last,
        target_contest=training_last + 1,
        variables=(TemporalVariable("history_prefix", training_last),),
        transforms=(FittedTransform("frequency_transform", training_last),),
    )


def test_t20_future_result_in_variables_blocks_experiment() -> None:
    window = BacktestWindow(
        window_id="t20-future-variable",
        training_last_contest=199,
        target_contest=200,
        variables=(
            TemporalVariable("history_prefix", 199),
            TemporalVariable("future_result_200", 200),
        ),
    )

    called = False

    def scorer(_: BacktestWindow) -> float:
        nonlocal called
        called = True
        return 0.20

    with pytest.raises(BacktestLeakageError, match="LOOKAHEAD_LEAKAGE_DETECTED"):
        run_audited_backtest((window,), scorer, min_successful_windows=1)

    assert called is False


def test_t21_transform_fit_on_full_history_is_detected() -> None:
    window = BacktestWindow(
        window_id="t21-full-history-transform",
        training_last_contest=249,
        target_contest=250,
        variables=(TemporalVariable("history_prefix", 249),),
        transforms=(FittedTransform("global_standardizer", 400),),
    )

    with pytest.raises(BacktestLeakageError, match="TRANSFORM_FIT_LEAKAGE_DETECTED"):
        run_audited_backtest((window,), lambda _: 0.20, min_successful_windows=1)


def test_t22_failed_window_remains_in_denominator_and_report() -> None:
    windows = tuple(_window(index) for index in range(5))

    def scorer(window: BacktestWindow) -> float:
        if window.window_id == "window-02":
            raise ArithmeticError("synthetic-window-failure")
        return 0.20

    report = run_audited_backtest(
        windows,
        scorer,
        min_successful_windows=4,
        min_success_rate=0.80,
    )

    assert report.status == "VALID"
    assert report.planned_windows == 5
    assert report.successful_windows == 4
    assert report.failed_windows == 1
    assert report.success_rate == 0.80
    assert len(report.outcomes) == 5
    failed = next(outcome for outcome in report.outcomes if outcome.state == "FAILED")
    assert failed.window_id == "window-02"
    assert failed.error_type == "ArithmeticError"
    assert failed.error_message == "synthetic-window-failure"
    assert all(outcome.m0_brier == 0.24 for outcome in report.outcomes)


def test_t23_small_sample_is_inconclusive_even_with_good_scores() -> None:
    windows = tuple(_window(index) for index in range(3))
    report = run_audited_backtest(
        windows,
        lambda _: 0.10,
        min_successful_windows=10,
        min_success_rate=0.80,
    )

    assert report.status == "INCONCLUSIVE"
    assert report.planned_windows == 3
    assert report.successful_windows == 3
    assert report.failed_windows == 0
    assert report.mean_delta_brier == pytest.approx(0.14)
    assert report.predictive_evidence == "NOT_ESTABLISHED"
