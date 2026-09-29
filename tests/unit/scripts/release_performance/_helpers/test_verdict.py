"""Tests for the release performance regression verdict."""

import pytest

from scripts.release_performance._helpers.verdict import (
    metric_verdicts,
    regression_messages,
    skip_reason,
)
from scripts.release_performance.models import BenchmarkCommand, MetricVerdict
from tests.unit.scripts.release_performance._helpers._test_types import (
    MetricVerdictTestCase,
    SkipReasonTestCase,
)
from tests.unit.scripts.release_performance._helpers.helpers import comparison


@pytest.mark.parametrize(
    "test_case",
    (
        MetricVerdictTestCase(
            description="identical medians pass",
            comparison=comparison(
                name="dag --json",
                baseline=((9.0, 9.0, 500),) * 3,
                candidate=((9.0, 9.0, 500),) * 3,
            ),
            expected_regressed=(False, False, False),
        ),
        MetricVerdictTestCase(
            description="slower planning with more peak memory fails CPU and RSS below wall limit",
            comparison=comparison(
                name="plan --json",
                baseline=((122.7, 125.6, 973),) * 3,
                candidate=((150.3, 157.3, 1_742),) * 3,
            ),
            expected_regressed=(False, True, True),
        ),
        MetricVerdictTestCase(
            description="a sub-second command doubling stays under the absolute floor",
            comparison=comparison(
                name="scope --json",
                baseline=((0.3, 0.3, 70),) * 3,
                candidate=((0.7, 0.7, 70),) * 3,
            ),
            expected_regressed=(False, False, False),
        ),
        MetricVerdictTestCase(
            description="a small allocation growth stays under the memory floor",
            comparison=comparison(
                name="lineage hub downstream",
                baseline=((2.0, 2.0, 40),) * 3,
                candidate=((2.0, 2.0, 70),) * 3,
            ),
            expected_regressed=(False, False, False),
        ),
        MetricVerdictTestCase(
            description="exactly the ratio limit passes and just above it fails",
            comparison=comparison(
                name="compile (warm cache)",
                baseline=((10.0, 10.0, 400),) * 3,
                candidate=((12.5, 12.6, 400),) * 3,
            ),
            expected_regressed=(False, True, False),
        ),
        MetricVerdictTestCase(
            description="one slow outlier does not move the median",
            comparison=comparison(
                name="build (empty warehouse)",
                baseline=((60.0, 60.0, 700),) * 3,
                candidate=((60.0, 60.0, 700), (95.0, 95.0, 1_400), (61.0, 61.0, 710)),
            ),
            expected_regressed=(False, False, False),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_command_samples_when_judging_then_flags_only_material_regressions(
    test_case: MetricVerdictTestCase,
) -> None:
    verdicts: tuple[MetricVerdict, ...] = metric_verdicts(comparison=test_case.comparison)

    assert tuple(verdict.metric for verdict in verdicts) == ("wall", "CPU", "peak RSS")
    assert tuple(verdict.regressed for verdict in verdicts) == test_case.expected_regressed
    messages: tuple[str, ...] = regression_messages(commands=(test_case.comparison,))
    assert len(messages) == sum(test_case.expected_regressed)
    for message in messages:
        assert message.startswith(f"{test_case.comparison.name}: ")


@pytest.mark.parametrize(
    "test_case",
    (
        SkipReasonTestCase(
            description="a command without a minimum version always runs",
            minimum_version=None,
            baseline_version="0.119.1",
            candidate_version="0.121.0",
            expected_reason=None,
        ),
        SkipReasonTestCase(
            description="a command newer than the baseline is skipped with the baseline named",
            minimum_version="0.126.0",
            baseline_version="0.125.1",
            candidate_version="0.126.0",
            expected_reason="requires sqlbuild 0.126.0 or later; baseline is 0.125.1",
        ),
        SkipReasonTestCase(
            description="versions compare numerically rather than as text",
            minimum_version="0.99.0",
            baseline_version="0.126.1",
            candidate_version="0.126.2",
            expected_reason=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_command_minimum_version_when_checking_versions_then_explains_skips(
    test_case: SkipReasonTestCase,
) -> None:
    command: BenchmarkCommand = BenchmarkCommand(
        name="dag --json",
        project="inspection",
        sqb_args=("dag", "--json"),
        minimum_version=test_case.minimum_version,
    )

    reason: str | None = skip_reason(
        command=command,
        baseline_version=test_case.baseline_version,
        candidate_version=test_case.candidate_version,
    )

    assert reason == test_case.expected_reason


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
