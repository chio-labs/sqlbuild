"""Tests for the same-runner compile ratio verdict across cold, warm and edit modes."""

import pytest

from scripts.compile_performance_ratio._helpers.verdict import ratio_failures
from scripts.compile_performance_ratio.constants import COMPILE_MODES, NOISE_FLOOR_SECONDS
from tests.unit.scripts.compile_performance_ratio._helpers._test_types import (
    RatioFailuresTestCase,
)
from tests.unit.scripts.compile_performance_ratio._helpers.helpers import comparison


@pytest.mark.parametrize(
    "test_case",
    [
        RatioFailuresTestCase(
            description="edit allowances leave cold and warm limits intact",
            comparisons=(),
            modes=COMPILE_MODES,
            max_ratio=1.10,
            expected_failures=(
                "dense 3000 cold: wall ratio 1.200 exceeds 1.10",
                "dense 3000 cold: CPU ratio 1.200 exceeds 1.10",
                "dense 3000 warm: wall ratio 1.200 exceeds 1.10",
                "dense 3000 warm: CPU ratio 1.200 exceeds 1.10",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_edit_cpu_override_when_judging_then_other_metrics_remain_gated(
    test_case: RatioFailuresTestCase,
) -> None:
    failures: tuple[str, ...] = ratio_failures(
        comparisons=(
            comparison(mode="cold", wall=(10.0, 12.0), cpu=(10.0, 12.0)),
            comparison(mode="warm", wall=(10.0, 12.0), cpu=(10.0, 12.0)),
            comparison(mode="edit", wall=(10.0, 12.0), cpu=(10.0, 17.5)),
        ),
        modes=COMPILE_MODES,
        max_ratio=1.10,
        noise_floor_seconds=0.0,
        mode_max_ratios={"edit": 1.20},
        mode_cpu_max_ratios={"edit": 1.75},
    )
    assert failures == test_case.expected_failures
    assert ratio_failures(
        comparisons=(comparison(mode="edit", wall=(10.0, 12.1), cpu=(10.0, 17.6)),),
        modes=("edit",),
        max_ratio=1.10,
        noise_floor_seconds=0.0,
        mode_max_ratios={"edit": 1.20},
        mode_cpu_max_ratios={"edit": 1.75},
    ) == (
        "dense 3000 edit: wall ratio 1.210 exceeds 1.20",
        "dense 3000 edit: CPU ratio 1.760 exceeds 1.75",
    )


@pytest.mark.parametrize(
    "test_case",
    (
        RatioFailuresTestCase(
            description="every mode at parity passes",
            comparisons=(
                comparison(mode="cold", wall=(18.0, 18.1), cpu=(40.0, 40.2)),
                comparison(mode="warm", wall=(7.6, 7.5), cpu=(9.1, 9.0)),
                comparison(mode="edit", wall=(8.6, 8.7), cpu=(11.0, 11.1)),
            ),
            modes=COMPILE_MODES,
            max_ratio=1.10,
            expected_failures=(),
        ),
        RatioFailuresTestCase(
            description="exactly the limit passes",
            comparisons=(comparison(mode="warm", wall=(8.0, 8.8), cpu=(10.0, 11.0)),),
            modes=("warm",),
            max_ratio=1.10,
            expected_failures=(),
        ),
        RatioFailuresTestCase(
            description="a warm-only slowdown fails while cold and edit pass",
            comparisons=(
                comparison(mode="cold", wall=(18.0, 18.0), cpu=(40.0, 40.0)),
                comparison(mode="warm", wall=(7.6, 11.4), cpu=(9.0, 13.5)),
                comparison(mode="edit", wall=(8.6, 8.6), cpu=(11.0, 11.0)),
            ),
            modes=COMPILE_MODES,
            max_ratio=1.10,
            expected_failures=(
                "dense 3000 warm: wall ratio 1.500 exceeds 1.10",
                "dense 3000 warm: CPU ratio 1.500 exceeds 1.10",
            ),
        ),
        RatioFailuresTestCase(
            description="an edit CPU regression at wall parity fails on CPU alone",
            comparisons=(comparison(mode="edit", wall=(8.0, 8.0), cpu=(10.0, 12.0)),),
            modes=("edit",),
            max_ratio=1.10,
            expected_failures=("dense 3000 edit: CPU ratio 1.200 exceeds 1.10",),
        ),
        RatioFailuresTestCase(
            description="a sub-second reused warm compile within the floor passes",
            comparisons=(comparison(mode="warm", wall=(0.56, 0.65), cpu=(0.44, 0.52)),),
            modes=("warm",),
            max_ratio=1.10,
            expected_failures=(),
        ),
        RatioFailuresTestCase(
            description="a sub-second reused warm compile beyond the floor fails",
            comparisons=(comparison(mode="warm", wall=(0.56, 0.85), cpu=(0.44, 0.44)),),
            modes=("warm",),
            max_ratio=1.10,
            expected_failures=("dense 3000 warm: wall ratio 1.518 exceeds 1.10",),
        ),
        RatioFailuresTestCase(
            description="an edit within its own looser limit passes while warm keeps the default",
            comparisons=(
                comparison(mode="warm", wall=(7.6, 7.6), cpu=(9.0, 9.0)),
                comparison(mode="edit", wall=(8.0, 10.0), cpu=(10.0, 12.0)),
            ),
            modes=("warm", "edit"),
            max_ratio=1.10,
            mode_max_ratios={"edit": 1.30},
            expected_failures=(),
        ),
        RatioFailuresTestCase(
            description="an edit beyond its own limit fails against that limit",
            comparisons=(comparison(mode="edit", wall=(8.0, 11.0), cpu=(10.0, 10.0)),),
            modes=("edit",),
            max_ratio=1.10,
            mode_max_ratios={"edit": 1.30},
            expected_failures=("dense 3000 edit: wall ratio 1.375 exceeds 1.30",),
        ),
        RatioFailuresTestCase(
            description="a requested mode without a measurement fails",
            comparisons=(comparison(mode="cold", wall=(18.0, 18.0), cpu=(40.0, 40.0)),),
            modes=("cold", "edit"),
            max_ratio=1.10,
            expected_failures=("edit: no measurement",),
        ),
        RatioFailuresTestCase(
            description="a zero base measurement fails as missing instead of dividing by zero",
            comparisons=(comparison(mode="warm", wall=(0.0, 7.5), cpu=(9.0, 9.0)),),
            modes=("warm",),
            max_ratio=1.10,
            expected_failures=(
                "dense 3000 warm: wall measurement missing (base 0.00 s, head 7.50 s)",
            ),
        ),
        RatioFailuresTestCase(
            description="a zero head measurement fails as missing instead of passing as fast",
            comparisons=(comparison(mode="cold", wall=(18.0, 18.0), cpu=(40.0, 0.0)),),
            modes=("cold",),
            max_ratio=1.10,
            expected_failures=(
                "dense 3000 cold: CPU measurement missing (base 40.00 s, head 0.00 s)",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mode_comparisons_when_judging_then_reports_each_failed_limit(
    test_case: RatioFailuresTestCase,
) -> None:
    failures: tuple[str, ...] = ratio_failures(
        comparisons=test_case.comparisons,
        modes=test_case.modes,
        max_ratio=test_case.max_ratio,
        noise_floor_seconds=NOISE_FLOOR_SECONDS,
        mode_max_ratios=test_case.mode_max_ratios,
    )

    assert failures == test_case.expected_failures


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
