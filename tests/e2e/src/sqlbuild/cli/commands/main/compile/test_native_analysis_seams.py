"""The analysis stage seams defer to Python, so every engine compiles a project identically."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeAnalysisSeamTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    engine_in_process_compile,
    prepare_compile_reuse_project,
    report_without_engine,
)

_ENGINES: tuple[str, ...] = ("python", "native", "native-preview")


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAnalysisSeamTestCase(
            description="models_contracts_lineage_and_sql_tests",
            expected_preview_returns={
                "assemble_native_project": [None],
                "analyze_native_model_sql": [None],
                "complete_native_semantic_diagnostics": [None],
                "evaluate_native_model_contracts": [None],
                "build_native_column_lineage": [None],
                "plan_native_sql_test_artifacts": [None],
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_compiling_with_each_engine_then_seams_defer_and_outputs_match(
    test_case: NativeAnalysisSeamTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    outcomes: dict[str, tuple[CompileReuseRun, dict[str, list[object]]]] = {
        engine: engine_in_process_compile(
            project_dir=copy_compile_project(
                source=prepared_project, destination=tmp_path / engine
            ),
            engine=engine,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        for engine in _ENGINES
    }
    python_run, python_seams = outcomes["python"]
    native_run, native_seams = outcomes["native"]
    preview_run, preview_seams = outcomes["native-preview"]

    assert python_run.returncode == 0, python_run.stderr
    assert python_run.compiled
    assert (python_seams, native_seams, preview_seams) == (
        {},
        {},
        test_case.expected_preview_returns,
    )
    assert (native_run.returncode, preview_run.returncode) == (0, 0)
    assert report_without_engine(native_run) == report_without_engine(python_run)
    assert report_without_engine(preview_run) == report_without_engine(python_run)
    assert native_run.compiled == python_run.compiled
    assert preview_run.compiled == python_run.compiled


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
