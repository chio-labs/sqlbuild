"""The differential harness passes identical engines and pinpoints a perturbed one."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import (
    CoverageFailureTestCase,
    HarnessRunTestCase,
    ProjectExpectationTestCase,
)
from tests.e2e.scripts.compiler_differential.helpers import (
    DISCOVERY_PERTURBATION,
    NATIVE_ONLY_STDERR_LINE,
    RENDER_PERTURBATION,
    harness_arguments,
    perturbation_arguments,
    write_broken_ref_project,
    write_failure_case_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="identical_engines",
            extra_arguments=(),
            expected_exit_code=0,
            expected_lines=(
                "OK   project/waffle_shop",
                "Compiler differential passed: 1 projects identical (python vs native-preview)",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_identical_engines_when_comparing_fixture_then_harness_passes(
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
        HarnessRunTestCase(
            description="perturbed_native_compiled_project",
            extra_arguments=(),
            expected_exit_code=1,
            expected_lines=(
                "DIFF project/waffle_shop",
                "- `compile` stdout at /resources/models/0/query_sql",
                'native-preview: "SELECT * FROM (',
                "- `compile` stderr at line 1",
                f'native-preview: "{NATIVE_ONLY_STDERR_LINE}"',
                "- stage capture 0-compile/003-compiled_project.json at /models/0/query_sql",
                "First difference: project/waffle_shop: `compile` stdout at",
            ),
            expected_patterns=(
                r"- target/compiled/models/\S+\.sql at line \d+",
                r"- query fingerprint of model \w+ \(manifest query hash\)",
                r"- query fingerprint of model \w+ \(plan version hash\)",
            ),
            expected_absent=("discovered_project_inputs.json", "compile_project_inputs.json"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_perturbed_native_engine_when_comparing_then_every_artifact_is_located(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=(*perturbation_arguments(tmp_path / "perturbation"), *test_case.extra_arguments),
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert all(re.search(pattern, output) for pattern in test_case.expected_patterns), output
    assert not any(text in output for text in test_case.expected_absent), output


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="perturbed_native_discovery",
            extra_arguments=(),
            expected_exit_code=1,
            expected_lines=("DIFF project/waffle_shop",),
            expected_patterns=(
                r"- stage capture 0-compile/001-discovered_project_inputs\.json at /model_files/0/",
                r"- stage capture 2-plan/001-discovered_project_inputs\.json at /model_files/0/",
            ),
            expected_absent=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_perturbed_native_discovery_when_comparing_then_discovery_capture_names_the_stage(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=perturbation_arguments(tmp_path / "perturbation", source=DISCOVERY_PERTURBATION),
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert all(re.search(pattern, output) for pattern in test_case.expected_patterns), output


@pytest.mark.parametrize(
    "test_case",
    [
        HarnessRunTestCase(
            description="perturbed_native_compile_inputs",
            extra_arguments=(),
            expected_exit_code=1,
            expected_lines=("DIFF project/waffle_shop",),
            expected_patterns=(
                r"- stage capture 0-compile/002-compile_project_inputs\.json at "
                r"/model_inputs/0/macro_deps/",
                r"- stage capture 2-plan/002-compile_project_inputs\.json at "
                r"/model_inputs/0/macro_deps/",
            ),
            expected_absent=("001-discovered_project_inputs.json",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_perturbed_native_render_when_comparing_then_compile_inputs_capture_names_the_stage(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=perturbation_arguments(tmp_path / "perturbation", source=RENDER_PERTURBATION),
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output
    assert all(re.search(pattern, output) for pattern in test_case.expected_patterns), output
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
def test_given_both_engines_fail_alike_when_outcome_is_unexpected_then_harness_fails(
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
                "Compiler differential FAILED: 0 of 1 projects differ",
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
                "Compiler differential FAILED: 0 of 1 projects differ",
                "Required render coverage missing: ",
            ),
            expected_absent=("passed", "Required discovery coverage missing"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_required_coverage_missing_when_comparing_then_harness_fails_and_says_so(
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
        HarnessRunTestCase(
            description="shared_analysis_seed_against_itself",
            extra_arguments=(
                "--corpus",
                "seeds",
                "--seed-start",
                "29",
                "--seeds",
                "1",
                "--engines",
                "python",
                "python",
                "--stage-captures",
            ),
            expected_exit_code=0,
            expected_lines=(
                "OK   seed/29",
                "Compiler differential passed: 1 projects identical (python vs python)",
            ),
            expected_patterns=(),
            expected_absent=("DIFF",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_engine_twice_when_capturing_stages_then_captures_are_identical(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
