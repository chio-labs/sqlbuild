"""The differential harness passes identical engines and pinpoints a perturbed one."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import (
    CoverageFailureTestCase,
    HarnessRunTestCase,
    ProjectExpectationTestCase,
    SharedAnalysisSeedTestCase,
    WheelSiteReportTestCase,
)
from tests.e2e.scripts.compiler_differential.helpers import (
    CATALOG_PERTURBATION,
    COMPILED_PROJECT_CAPTURE,
    DEFERRAL_PERTURBATION,
    DISCOVERY_PERTURBATION,
    NATIVE_ONLY_STDERR_LINE,
    RENDER_PERTURBATION,
    SHARED_ANALYSIS_SEED,
    harness_arguments,
    perturbation_arguments,
    shared_analysis_seed_arguments,
    write_broken_ref_project,
    write_failure_case_project,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    CompiledProjectRun,
    compiled_project_capture,
    use_wave_analysis,
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
                r"- stage capture 3-plan/001-discovered_project_inputs\.json at /model_files/0/",
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
                r"- stage capture 2-compile-store-warm/002-compile_project_inputs\.json at "
                r"/model_inputs/0/macro_deps/",
                r"- stage capture 3-plan/002-compile_project_inputs\.json at "
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
        HarnessRunTestCase(
            description="wrong_native_catalog_shape",
            extra_arguments=(),
            expected_exit_code=1,
            expected_lines=("DIFF project/waffle_shop",),
            expected_patterns=(
                r"- stage capture 0-compile/\d+-compiled_project\.json at /binding_catalog/schemas",
            ),
            expected_absent=("warm/", "3-plan/"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wrong_native_catalog_shape_when_comparing_then_only_the_cold_capture_differs(
    test_case: HarnessRunTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=perturbation_arguments(tmp_path / "perturbation", source=CATALOG_PERTURBATION),
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
        SharedAnalysisSeedTestCase(
            description="shared_analysis_seed_against_itself",
            seed=SHARED_ANALYSIS_SEED,
            expected_lines=(
                f"OK   seed/{SHARED_ANALYSIS_SEED}",
                "Compiler differential passed: 3 projects identical (python vs python)",
            ),
            expected_capture_sides=("left-python-captures", "right-python-captures"),
            expected_compile_exit_code=0,
            expected_minimum_shareable_members=1,
            expected_minimum_shared_reuse=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_engine_twice_when_capturing_stages_then_captures_are_identical(
    test_case: SharedAnalysisSeedTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir: Path = tmp_path / "work"
    exit_code: int = run_compiler_differential(
        shared_analysis_seed_arguments(work_dir=work_dir, seed=test_case.seed)
    )
    output: str = capsys.readouterr().out
    seed_dir: Path = work_dir / f"seed__{test_case.seed}"
    project_dir: Path = Path(shutil.copytree(seed_dir / "source", tmp_path / "project"))
    with monkeypatch.context() as waves_patch:
        use_wave_analysis(waves_patch)
        compiled: CompiledProjectRun = compiled_project_capture(
            project_dir=project_dir,
            capture_dir=tmp_path / "captures",
            capsys=capsys,
            monkeypatch=waves_patch,
        )

    assert (exit_code, all(line in output for line in test_case.expected_lines)) == (0, True), (
        output
    )
    assert "DIFF" not in output, output
    assert all(
        (seed_dir / side / COMPILED_PROJECT_CAPTURE).is_file()
        for side in test_case.expected_capture_sides
    ), output
    assert (
        compiled.exit_code,
        compiled.shareable_members >= test_case.expected_minimum_shareable_members,
        compiled.shared_reuse >= test_case.expected_minimum_shared_reuse,
    ) == (test_case.expected_compile_exit_code, True, True), compiled


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


@pytest.mark.parametrize(
    "test_case",
    [
        WheelSiteReportTestCase(
            description="python_and_preview_wheel_calls_without_preview_deferrals",
            perturbation="",
            expected_lines=(
                "Polyglot wheel calls (python):",
                "Polyglot wheel calls (native-preview):",
                "Analysis deferrals (python): none recorded",
                "Analysis deferrals (native-preview): none recorded",
                "Compiler differential passed: 1 projects identical",
            ),
            expected_sites=frozenset(
                {
                    "compiler/compile/_helpers/analysis/validation.py:"
                    "_validate_sql_syntax_with_message parse_one",
                }
            ),
            expected_deferrals=frozenset(),
        ),
        WheelSiteReportTestCase(
            description="preview_deferrals_are_counted_per_kind_and_site",
            perturbation=DEFERRAL_PERTURBATION,
            expected_lines=(
                "Analysis deferrals (python): none recorded",
                "Analysis deferrals (native-preview):",
                " legacy_fallback orders.sql (project ",
            ),
            expected_sites=frozenset(),
            expected_deferrals=frozenset({"legacy_fallback orders.sql"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_wheel_site_report_when_comparing_then_sites_and_deferrals_are_reported(
    test_case: WheelSiteReportTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path: Path = tmp_path / "report" / "wheel-sites.json"
    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "work",
            extra=(
                *perturbation_arguments(tmp_path / "perturbation", source=test_case.perturbation),
                "--wheel-site-report",
                str(report_path),
            ),
        )
    )

    output: str = capsys.readouterr().out
    report: dict[str, dict[str, dict[str, dict[str, int]]]] = json.loads(
        report_path.read_text(encoding="utf-8")
    )
    preview: dict[str, dict[str, dict[str, int]]] = report["native-preview"]
    assert exit_code == 0, output
    assert all(line in output for line in test_case.expected_lines), output
    assert test_case.expected_sites <= set(report["python"]["wheel_sites"]), report
    assert set(preview["deferrals"]) == test_case.expected_deferrals
    assert all(sum(by_corpus.values()) > 0 for by_corpus in preview["deferrals"].values())
    assert report["python"]["deferrals"] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
