"""Column inference outside the analysis session: models native analysis cannot project and
table-function bodies keep the columns Python's parsed-tree inference gave them.

Expected outputs recorded from the pre-port Python `infer_columns_with_sql_analysis`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild._native as native_module
import sqlbuild.compiler.compile._helpers.assembly.project as project_assembly
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    FallbackColumnsTestCase,
    MissingSessionAnalysisTestCase,
    TableFunctionColumnsTestCase,
)
from tests.integration.src.sqlbuild.compiler.lineage.helpers import compiled_project

_PROJECT: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
_HEADER: str = "MODEL (description 'Test model.', materialized view);\n"


@pytest.mark.parametrize(
    "test_case",
    [
        FallbackColumnsTestCase(
            description="CREATE TABLE AS takes its inner select's columns",
            query_sql="CREATE TABLE t AS SELECT 1 AS a",
            expected_columns=(("a", None, "non_null"),),
        ),
        FallbackColumnsTestCase(
            description="INSERT ... SELECT takes its select's columns",
            query_sql="INSERT INTO t SELECT 1 AS a",
            expected_columns=(("a", None, "non_null"),),
        ),
        FallbackColumnsTestCase(
            description="calls nested 200 deep",
            query_sql="SELECT " + "f(" * 200 + "1" + ")" * 200 + " AS deep",
            expected_columns=(("deep", None, "unknown"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unprojectable_model_when_compiling_then_parsed_tree_columns_are_kept(
    test_case: FallbackColumnsTestCase, tmp_path: Path
) -> None:
    project: CompiledProject = compiled_project(
        project_dir=tmp_path,
        files={
            "sqlbuild_project.toml": _PROJECT,
            "models/orders.sql": _HEADER + test_case.query_sql,
        },
    )
    model: CompiledModel = project.models[0]

    assert (
        None
        if model.inferred_columns is None
        else tuple(
            (column.name, column.type, column.nullability.value)
            for column in model.inferred_columns
        )
    ) == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        TableFunctionColumnsTestCase(
            description="matching return columns",
            returns="table (id INTEGER, label VARCHAR)",
            body_sql="SELECT x AS id, 'a' AS label",
            expected_error=None,
        ),
        TableFunctionColumnsTestCase(
            description="fewer body columns than declared",
            returns="table (id INTEGER, label VARCHAR)",
            body_sql="SELECT x AS id",
            expected_error=(
                "SQL table function functions/sql/table_fn__orders.sql declares 2 return "
                "columns but its query produces 1"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_when_compiling_then_body_columns_match_declaration(
    test_case: TableFunctionColumnsTestCase, tmp_path: Path
) -> None:
    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT,
        "functions/sql/table_fn__orders.sql": (
            "FUNCTION (description 'Test function.', arguments (x INTEGER), "
            f"returns {test_case.returns}); {test_case.body_sql}"
        ),
    }
    error: str | None = None
    try:
        _ = compiled_project(project_dir=tmp_path, files=files)
    except CompileInputError as raised:
        error = str(raised)

    assert error == test_case.expected_error


@pytest.mark.parametrize(
    "test_case",
    [
        MissingSessionAnalysisTestCase(
            description="a requested model the session left unanalysed",
            expected_message=(
                "NativeCompilerError: native model analysis: the session returned no analysis "
                "for model 'orders'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_session_without_model_analysis_when_assembling_then_raises_native_compiler_error(
    test_case: MissingSessionAnalysisTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_assembly, "analyze_model_sql", lambda _request: ({}, None))

    with pytest.raises(native_module.NativeCompilerError) as raised:
        _ = compiled_project(
            project_dir=tmp_path,
            files={
                "sqlbuild_project.toml": _PROJECT,
                "models/orders.sql": _HEADER + "SELECT 1 AS a",
            },
        )

    assert str(raised.value) == test_case.expected_message


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
