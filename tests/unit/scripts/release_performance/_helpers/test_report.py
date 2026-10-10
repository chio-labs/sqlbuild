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
            description="temporary RSS allowances are reported for each affected command",
            commands=(
                comparison(
                    name="lineage column trace",
                    baseline=((10.0, 10.0, 400),) * 3,
                    candidate=((10.0, 10.0, 800),) * 3,
                    max_rss_ratio=2.0,
                ),
                comparison(
                    name="dag --json",
                    baseline=((10.0, 10.0, 400),) * 3,
                    candidate=((10.0, 10.0, 601),) * 3,
                    max_rss_ratio=1.5,
                ),
            ),
            skipped=(),
            expected_fragments=(
                "Peak RSS limit for `lineage column trace`: 2.00x "
                "(+100%; temporary memory exception).",
                "Peak RSS limit for `dag --json`: 1.50x (+50%; temporary memory exception).",
                "| 400 → 800 | 2.000x | ✅ ok |",
                "**Result: failed.** dag --json: peak RSS 1.502x exceeds 1.50x.",
            ),
            unexpected_fragments=("lineage column trace: peak RSS",),
        ),
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
                "peak RSS +25% (ignored under 32 MiB). Cold, warm and one-model edit compiles "
                "use +15% for wall and CPU.",
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
            description="a compile regression is judged against the compile time limit",
            commands=(
                comparison(
                    name="compile (one-model edit)",
                    baseline=((6.0, 7.0, 450),) * 3,
                    candidate=((7.2, 7.1, 450),) * 3,
                    max_time_ratio=1.15,
                ),
            ),
            skipped=(),
            expected_fragments=(
                "| `compile (one-model edit)` | 6.00 → 7.20 | **1.200x** | 7.00 → 7.10 | 1.014x "
                "| 450 → 450 | 1.000x | ❌ regressed |",
                "**Result: failed.** compile (one-model edit): wall 1.200x exceeds 1.15x.",
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
