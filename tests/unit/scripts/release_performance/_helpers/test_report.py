"""Tests for the release performance job summary."""

import pytest

from scripts.release_performance._helpers.report import comparison_markdown
from scripts.release_performance.models import (
    ReleaseComparison,
    RunnerContext,
    SkippedCommand,
)
from tests.unit.scripts.release_performance._helpers._test_types import (
    ComparisonMarkdownTestCase,
)
from tests.unit.scripts.release_performance._helpers.helpers import comparison


@pytest.mark.parametrize(
    "test_case",
    (
        ComparisonMarkdownTestCase(
            description="a passing comparison lists every command and the limits",
            commands=(
                comparison(
                    name="compile (warm cache)",
                    baseline=((6.0, 6.5, 500),) * 3,
                    candidate=((6.1, 6.4, 505),) * 3,
                ),
            ),
            skipped=(),
            expected_fragments=(
                "### Release performance: 0.126.2 (candidate) vs 0.126.1 (baseline)",
                "Same runner: Example CPU, 4 CPUs; load average 0.50/0.40/0.30 before",
                "3 interleaved runs per version",
                "Benchmark projects are generated per side: the baseline runs projects from its "
                "own generator (v0.126.1), the candidate from the candidate's.",
                "Limits: wall +25% (ignored under 0.5 s), CPU +25% (ignored under 0.5 s), "
                "peak RSS +25% (ignored under 32 MiB).",
                "| `compile (warm cache)` | 6.00 → 6.10 | 1.017x | 6.50 → 6.40 | 0.985x "
                "| 500 → 505 | 1.010x | ✅ ok |",
                "**Result: passed.**",
            ),
            unexpected_fragments=("❌", "skipped"),
        ),
        ComparisonMarkdownTestCase(
            description="a regression is bolded and named in the failed result",
            commands=(
                comparison(
                    name="plan --json",
                    baseline=((27.0, 28.0, 900),) * 3,
                    candidate=((56.0, 57.0, 1_800),) * 3,
                ),
            ),
            skipped=(),
            expected_fragments=(
                "| `plan --json` | 27.00 → 56.00 | **2.074x** | 28.00 → 57.00 | **2.036x** "
                "| 900 → 1800 | **2.000x** | ❌ regressed |",
                "**Result: failed.** plan --json: wall 2.074x exceeds 1.25x; plan --json: CPU "
                "2.036x exceeds 1.25x; plan --json: peak RSS 2.000x exceeds 1.25x.",
            ),
            unexpected_fragments=("**Result: passed.**",),
        ),
        ComparisonMarkdownTestCase(
            description="a skipped command is reported with its reason instead of omitted",
            commands=(),
            skipped=(
                SkippedCommand(
                    name="scope --json",
                    reason="requires sqlbuild 0.126.2 or later; baseline is 0.126.1",
                ),
            ),
            expected_fragments=(
                "| `scope --json` | – | – | – | – | – | – | ⚠️ skipped: requires sqlbuild "
                "0.126.2 or later; baseline is 0.126.1 |",
                "**1 command(s) skipped** because a compared version predates them",
            ),
            unexpected_fragments=("❌",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_release_comparison_when_rendering_summary_then_reports_each_command(
    test_case: ComparisonMarkdownTestCase,
) -> None:
    release: ReleaseComparison = ReleaseComparison(
        baseline_version="0.126.1",
        candidate_version="0.126.2",
        baseline_generator="v0.126.1",
        runs=3,
        runner=RunnerContext(
            cpu_model="Example CPU",
            cpu_count=4,
            load_average_before=(0.5, 0.4, 0.3),
            load_average_after=(0.6, 0.5, 0.4),
        ),
        commands=test_case.commands,
        skipped=test_case.skipped,
    )

    markdown: str = comparison_markdown(comparison=release)

    for fragment in test_case.expected_fragments:
        assert fragment in markdown
    for fragment in test_case.unexpected_fragments:
        assert fragment not in markdown


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
