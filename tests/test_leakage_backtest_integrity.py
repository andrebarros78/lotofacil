from __future__ import annotations

import pytest

from sare_lotofacil.experiments.integrity import (
    TemporalIntegrityViolation,
    audit_backtest_windows,
)
from sare_lotofacil.experiments.protocol import ExperimentProtocol


def _protocol(**overrides) -> ExperimentProtocol:
    payload = {
        "hypothesis_id": "h-integrity",
        "question": "O protocolo temporal é íntegro?",
        "h0": "Sem vantagem",
        "h1": "Há vantagem",
        "snapshot_id": "snap-test",
    }
    payload.update(overrides)
    return ExperimentProtocol(**payload)


def test_t20_future_or_target_feature_is_blocked_before_experiment() -> None:
    protocol = _protocol(feature_offsets=(-1, 0))

    with pytest.raises(TemporalIntegrityViolation) as exc_info:
        _ = protocol.protocol_hash

    assert exc_info.value.code == "FUTURE_OR_TARGET_FEATURE_OFFSET"
    assert "FUTURE_OR_TARGET_FEATURE_OFFSET" in str(exc_info.value)


def test_t21_transform_fitted_on_full_history_is_blocked() -> None:
    protocol = _protocol(transform_fit_scope="FULL_HISTORY")

    with pytest.raises(TemporalIntegrityViolation) as exc_info:
        protocol.validate()

    assert exc_info.value.code == "TRANSFORM_FIT_OUTSIDE_TRAIN"


def test_t22_failed_backtest_window_stays_in_denominator_and_report() -> None:
    windows = tuple(f"window-{index:02d}" for index in range(35))

    def evaluator(window_id: str) -> float:
        if window_id == "window-11":
            raise RuntimeError("synthetic window failure")
        return 0.24

    values, report = audit_backtest_windows(
        windows,
        evaluator,
        min_required_windows=30,
    )

    assert len(values) == 34
    assert report.total_windows == 35
    assert report.successful_windows == 34
    assert report.failed_windows == 1
    assert report.failures[0].window_id == "window-11"
    assert "synthetic window failure" in report.failures[0].reason
    assert report.status == "INCONCLUSIVE_WINDOW_FAILURES"
    assert report.advantage_eligible is False


def test_t23_few_windows_are_inconclusive_and_never_approve_advantage() -> None:
    windows = tuple(f"window-{index:02d}" for index in range(5))
    values, report = audit_backtest_windows(
        windows,
        lambda _: 0.20,
        min_required_windows=30,
    )

    assert len(values) == 5
    assert report.total_windows == 5
    assert report.successful_windows == 5
    assert report.failed_windows == 0
    assert report.status == "INCONCLUSIVE_INSUFFICIENT_WINDOWS"
    assert report.advantage_eligible is False
