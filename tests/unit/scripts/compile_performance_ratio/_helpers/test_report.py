"""Tests for the same-runner compile comparison job summary."""

import pytest

from scripts.compile_performance_ratio._helpers.report import comparison_markdown
from tests.unit.scripts.compile_performance_ratio._helpers._test_types import (
    ComparisonMarkdownTestCase,
)
from tests.unit.scripts.compile_performance_ratio._helpers.helpers import comparison


@pytest.mark.parametrize(
    "test_case",
    (
        ComparisonMarkdownTestCase(
            description="every mode gets its own table and a passing result",
            comparisons=(
                comparison(mode="cold", wall=(18.0, 18.0), cpu=(40.0, 40.0)),
                comparison(mode="warm", wall=(7.6, 7.6), cpu=(9.0, 9.0)),
                comparison(mode="edit", wall=(8.0, 8.4), cpu=(11.0, 11.0)),
            ),
            failures=(),
            expected_fragments=(
                "### dense 3000 models, cold compile without cache: head vs base (same runner)",
                "### dense 3000 models, unchanged warm compile: head vs base (same runner)",
                "### dense 3000 models, one-model edit on a warm cache: head vs base",
                "| Wall (s) | 8.00 | 8.40 | 1.050 |",
                "| total_ms | 7600 | 7600 | 1.000 |",
                "**Result: passed.** Every mode is within the same-runner limit.",
            ),
        ),
        ComparisonMarkdownTestCase(
            description="failures are listed in the result",
            comparisons=(comparison(mode="warm", wall=(7.6, 11.4), cpu=(9.0, 9.0)),),
            failures=("dense 3000 warm: wall ratio 1.500 exceeds 1.10",),
            expected_fragments=(
                "| Wall (s) | 7.60 | 11.40 | 1.500 |",
                "**Result: failed.** dense 3000 warm: wall ratio 1.500 exceeds 1.10.",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mode_comparisons_when_rendering_summary_then_reports_each_mode(
    test_case: ComparisonMarkdownTestCase,
) -> None:
    markdown: str = comparison_markdown(
        comparisons=test_case.comparisons,
        runs=3,
        max_ratio=1.10,
        per_side_projects=True,
        failures=test_case.failures,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in markdown


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
