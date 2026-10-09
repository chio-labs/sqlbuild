"""Every engine compiles a project identically, whichever analysis stages run natively."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, Mock

import pytest

import sqlbuild._native as native_module
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact
from sqlbuild.compiler.project_assembly.models import NativeProjectResources
from sqlbuild.compiler.sql_test_glue.models import NativeSqlTestAssembly
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
                "assemble_native_project_resources": [ANY],
                "infer_native_expression_source_shapes": [ANY],
                "analyze_native_model_sql": [ANY],
                "assemble_native_sql_tests": [ANY],
                "complete_native_semantic_diagnostics": [ANY],
                "evaluate_native_model_contracts": [ANY],
                "native_promotion_conflict_diagnostics": [()],
                "build_native_column_lineage": [ANY],
                "plan_native_sql_test_artifacts": [ANY],
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_compiling_with_each_engine_then_native_seams_answer_and_outputs_match(
    test_case: NativeAnalysisSeamTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    native_sql_test_planning: Mock = Mock(wraps=native_module.plan_compiled_sql_tests)
    monkeypatch.setattr(native_module, "plan_compiled_sql_tests", native_sql_test_planning)
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
    assert isinstance(preview_seams["build_native_column_lineage"][0], ProjectColumnLineage)
    assert isinstance(preview_seams["assemble_native_project_resources"][0], NativeProjectResources)
    assert isinstance(preview_seams["analyze_native_model_sql"][0], dict)
    assert isinstance(preview_seams["infer_native_expression_source_shapes"][0], tuple)
    assembled_tests: object = preview_seams["assemble_native_sql_tests"][0]
    assert isinstance(assembled_tests, tuple)
    assert assembled_tests
    assert all(isinstance(assembled, NativeSqlTestAssembly) for assembled in assembled_tests)
    planned_artifacts: object = preview_seams["plan_native_sql_test_artifacts"][0]
    assert isinstance(planned_artifacts, tuple)
    assert planned_artifacts
    assert all(isinstance(artifact, NativeSqlTestArtifact) for artifact in planned_artifacts)
    assert [len(call.args[0].tests) for call in native_sql_test_planning.call_args_list] == [
        len(planned_artifacts)
    ]
    assert isinstance(preview_seams["complete_native_semantic_diagnostics"][0], CompiledProject)
    assert isinstance(preview_seams["evaluate_native_model_contracts"][0], ContractValidationResult)
    assert (native_run.returncode, preview_run.returncode) == (0, 0)
    assert report_without_engine(native_run) == report_without_engine(python_run)
    assert report_without_engine(preview_run) == report_without_engine(python_run)
    assert native_run.compiled == python_run.compiled
    assert preview_run.compiled == python_run.compiled


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
