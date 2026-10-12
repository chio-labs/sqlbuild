"""Every analysis stage seam answers natively when a project compiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, Mock

import pytest

import sqlbuild._native as native_module
from sqlbuild.compiler.analysis_session.models import NativeModelAnalyses
from sqlbuild.compiler.contracts.models import ContractValidationResult
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact
from sqlbuild.compiler.project_assembly.models import NativeProjectResources
from sqlbuild.compiler.sql_test_glue.models import NativeSqlTestAssembly
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeAnalysisSeamTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_compile_reuse_project,
    seam_recording_compile,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAnalysisSeamTestCase(
            description="models_contracts_lineage_and_sql_tests",
            expected_native_returns={
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
def test_given_project_when_compiling_then_native_seams_answer(
    test_case: NativeAnalysisSeamTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    native_sql_test_planning: Mock = Mock(wraps=native_module.plan_compiled_sql_tests)
    monkeypatch.setattr(native_module, "plan_compiled_sql_tests", native_sql_test_planning)
    native_run, native_seams = seam_recording_compile(
        project_dir=prepared_project, monkeypatch=monkeypatch, capsys=capsys
    )

    assert native_run.returncode == 0, native_run.stderr
    assert native_run.compiled
    assert native_seams == test_case.expected_native_returns
    planned_counts: list[int] = []
    for seams in (native_seams,):
        assert isinstance(seams["build_native_column_lineage"][0], ProjectColumnLineage)
        assert isinstance(seams["assemble_native_project_resources"][0], NativeProjectResources)
        assert isinstance(seams["analyze_native_model_sql"][0], NativeModelAnalyses)
        assert seams["analyze_native_model_sql"][0].session is not None
        assert isinstance(seams["infer_native_expression_source_shapes"][0], tuple)
        assembled_tests: object = seams["assemble_native_sql_tests"][0]
        assert isinstance(assembled_tests, tuple)
        assert assembled_tests
        assert all(isinstance(assembled, NativeSqlTestAssembly) for assembled in assembled_tests)
        planned_artifacts: object = seams["plan_native_sql_test_artifacts"][0]
        assert isinstance(planned_artifacts, tuple)
        assert planned_artifacts
        assert all(isinstance(artifact, NativeSqlTestArtifact) for artifact in planned_artifacts)
        planned_counts.append(len(planned_artifacts))
        assert isinstance(
            seams["complete_native_semantic_diagnostics"][0], native_module.NativeProjectView
        )
        assert isinstance(seams["evaluate_native_model_contracts"][0], ContractValidationResult)
    assert [
        len(call.args[0].tests) for call in native_sql_test_planning.call_args_list
    ] == planned_counts


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
