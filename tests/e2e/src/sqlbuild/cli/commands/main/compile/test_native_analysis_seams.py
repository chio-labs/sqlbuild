"""Every analysis stage seam answers natively when a project compiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY

import pytest

import sqlbuild._native as native_module
from sqlbuild._native import (
    ContractValidationResult,
    NativeSqlTestArtifact,
    ProjectColumnLineage,
)
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
                "infer_native_expression_source_shapes": [ANY, ANY, ANY],
                "evaluate_model_contracts": [ANY],
                "build_project_column_lineage": [ANY],
                "plan_compiled_sql_test_artifacts": [ANY],
            },
            expected_stage_work={
                "infer_native_expression_source_shapes": 1,
                "analyze_native_model_sql": 1,
                "complete_semantic_project": 1,
                "assemble_native_sql_tests": 1,
                "promotion_conflict_diagnostics": 1,
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
    native_run, native_seams = seam_recording_compile(
        project_dir=prepared_project, monkeypatch=monkeypatch, capsys=capsys
    )

    assert native_run.returncode == 0, native_run.stderr
    assert native_run.compiled
    assert native_seams == test_case.expected_native_returns
    stage_work: dict[str, int] = native_module.compile_stage_work_info()
    assert {
        stage: stage_work.get(stage, 0) for stage in test_case.expected_stage_work
    } == test_case.expected_stage_work
    for seams in (native_seams,):
        assert isinstance(seams["build_project_column_lineage"][0], ProjectColumnLineage)
        assert isinstance(seams["infer_native_expression_source_shapes"][0], tuple)
        planned_artifacts: object = seams["plan_compiled_sql_test_artifacts"][0]
        assert isinstance(planned_artifacts, tuple)
        assert planned_artifacts
        assert all(isinstance(artifact, NativeSqlTestArtifact) for artifact in planned_artifacts)
        assert isinstance(seams["evaluate_model_contracts"][0], ContractValidationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
