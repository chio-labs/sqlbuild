"""The harness reports how much of the discovery input space the seed corpus exercised."""

from __future__ import annotations

import pytest

from scripts.compiler_differential._helpers.running.report import (
    format_discovery_coverage,
    format_summary,
)
from scripts.compiler_differential.models import Difference, ProjectComparison
from tests.unit.scripts.compiler_differential._helpers.running._test_types import (
    CoverageReportTestCase,
    SummaryTestCase,
)

_IDENTICAL: ProjectComparison = ProjectComparison(project="seed/0", differences=(), seconds=1.0)
_DIFFERING: ProjectComparison = ProjectComparison(
    project="seed/1",
    differences=(
        Difference(
            project="seed/1", artifact="`compile` stdout", location="/models/0", left="a", right="b"
        ),
    ),
    seconds=1.0,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CoverageReportTestCase(
            description="complete",
            covered=frozenset({"model_files", "crlf"}),
            required=("model_files", "crlf"),
            expected_lines=(
                "Discovery coverage: 2 of 2 input kinds exercised by the seed corpus",
                "config-only kinds: project_adapter_config (only proves the config names",
            ),
        ),
        CoverageReportTestCase(
            description="missing_kinds_are_named_in_required_order",
            covered=frozenset({"model_files"}),
            required=("providers", "model_files", "crlf"),
            expected_lines=(
                "Discovery coverage: 1 of 3 input kinds exercised by the seed corpus",
                "  missing: providers, crlf",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_covered_kinds_when_reporting_then_missing_kinds_are_named(
    test_case: CoverageReportTestCase,
) -> None:
    report: str = format_discovery_coverage(covered=test_case.covered, required=test_case.required)

    assert all(line in report for line in test_case.expected_lines), report


@pytest.mark.parametrize(
    "test_case",
    [
        SummaryTestCase(
            description="identical_and_covered",
            comparisons=[_IDENTICAL],
            missing_coverage=(),
            expected_lines=("Compiler differential passed: 1 projects identical",),
            expected_absent=("FAILED",),
        ),
        SummaryTestCase(
            description="identical_but_coverage_missing",
            comparisons=[_IDENTICAL],
            missing_coverage=("providers", "crlf"),
            expected_lines=(
                "Compiler differential FAILED: 0 of 1 projects differ",
                "Required discovery coverage missing: providers, crlf",
            ),
            expected_absent=("passed",),
        ),
        SummaryTestCase(
            description="differences_and_coverage_missing",
            comparisons=[_IDENTICAL, _DIFFERING],
            missing_coverage=("providers",),
            expected_lines=(
                "Compiler differential FAILED: 1 of 2 projects differ",
                "First difference: seed/1: `compile` stdout at /models/0",
                "Required discovery coverage missing: providers",
            ),
            expected_absent=("passed",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_results_and_coverage_when_summarizing_then_failures_never_read_as_passed(
    test_case: SummaryTestCase,
) -> None:
    summary: str = format_summary(
        comparisons=test_case.comparisons,
        engines=("python", "native"),
        seconds=2.0,
        missing_coverage=test_case.missing_coverage,
    )

    assert all(line in summary for line in test_case.expected_lines), summary
    assert not any(text in summary for text in test_case.expected_absent), summary


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
