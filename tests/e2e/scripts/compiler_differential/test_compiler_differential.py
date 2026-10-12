"""The harness passes a healthy project and fails unexpected outcomes or missing coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import (
    CoverageFailureTestCase,
    HarnessRunTestCase,
    ProjectExpectationTestCase,
)
from tests.e2e.scripts.compiler_differential.helpers import (
    harness_arguments,
    write_broken_ref_project,
    write_failure_case_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="healthy_fixture",
            extra_arguments=(),
            expected_exit_code=0,
            expected_lines=(
                "OK   project/waffle_shop",
                "Compiler differential passed: 1 projects as expected",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_healthy_fixture_when_checking_then_harness_passes(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(work_dir=tmp_path / "work", extra=test_case.extra_arguments)
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert not any(text in output for text in test_case.expected_absent), output


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectExpectationTestCase(
            description="success_expected_by_default",
            extra_arguments=(),
            expected_exit_code=1,
            expected_lines=(
                "DIFF project/broken_orders",
                "- corpus expectation at expected success",
            ),
        ),
        ProjectExpectationTestCase(
            description="declared_failure_code",
            extra_arguments=("--expect", "failure:P001"),
            expected_exit_code=0,
            expected_lines=("OK   project/broken_orders",),
        ),
        ProjectExpectationTestCase(
            description="wrong_failure_code",
            extra_arguments=("--expect", "failure:P010"),
            expected_exit_code=1,
            expected_lines=(
                "DIFF project/broken_orders",
                "- corpus expectation at expected failure",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_outcome_when_it_is_unexpected_then_harness_fails(
    test_case: ProjectExpectationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=test_case.extra_arguments,
            project=write_broken_ref_project(tmp_path / "broken_orders"),
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


@pytest.mark.parametrize(
    "test_case",
    [
        CoverageFailureTestCase(
            description="one_seed_cannot_cover_every_kind",
            extra_arguments=(
                "--corpus",
                "seeds",
                "--seeds",
                "1",
                "--stage-captures",
                "--require-discovery-coverage",
            ),
            expected_exit_code=1,
            expected_lines=(
                "OK   seed/0",
                "Compiler differential FAILED: 0 of 3 projects differ",
                "Required discovery coverage missing: ",
            ),
            expected_absent=("passed",),
        ),
        CoverageFailureTestCase(
            description="one_seed_cannot_cover_every_render_kind",
            extra_arguments=(
                "--corpus",
                "seeds",
                "--seeds",
                "1",
                "--stage-captures",
                "--require-render-coverage",
            ),
            expected_exit_code=1,
            expected_lines=(
                "OK   seed/0",
                "Render coverage: ",
                "Compiler differential FAILED: 0 of 3 projects differ",
                "Required render coverage missing: ",
            ),
            expected_absent=("passed", "Required discovery coverage missing"),
        ),
        CoverageFailureTestCase(
            description="one_seed_cannot_cover_every_analysis_kind",
            extra_arguments=(
                "--corpus",
                "seeds",
                "--seeds",
                "1",
                "--stage-captures",
                "--require-analysis-coverage",
            ),
            expected_exit_code=1,
            expected_lines=(
                "OK   seed/0",
                "OK   seed/0-postgres",
                "OK   seed/0-snowflake",
                "Analysis coverage: ",
                "Compiler differential FAILED: 0 of 3 projects differ",
                "Required analysis coverage missing: ",
            ),
            expected_absent=("passed", "Required render coverage missing"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_required_coverage_missing_when_checking_then_harness_fails_and_says_so(
    test_case: CoverageFailureTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        ["--jobs", "1", "--work-dir", str(tmp_path / "work"), *test_case.extra_arguments]
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert not any(text in output for text in test_case.expected_absent), output


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectExpectationTestCase(
            description="expected_code_only_reported_as_warning",
            extra_arguments=("--expect", "failure:P003"),
            expected_exit_code=1,
            expected_lines=(
                "DIFF project/built-in-audit-shadow",
                "- corpus expectation at expected failure",
            ),
        ),
        ProjectExpectationTestCase(
            description="expected_code_is_the_first_error",
            extra_arguments=("--expect", "failure:S010"),
            expected_exit_code=0,
            expected_lines=("OK   project/built-in-audit-shadow",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failure_expectation_when_code_is_not_the_first_error_then_harness_fails(
    test_case: ProjectExpectationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=test_case.extra_arguments,
            project=write_failure_case_project(
                tmp_path / "built-in-audit-shadow", name="built-in-audit-shadow"
            ),
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
