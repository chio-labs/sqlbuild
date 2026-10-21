"""Python-built compiled models are read by attribute, and each such read is counted."""

from __future__ import annotations

import pytest

import sqlbuild._native as native
from sqlbuild._native import ProjectColumnLineage
from sqlbuild.compiler.compile.types import CompiledModelView
from tests.unit.src.sqlbuild.compiler.lineage._test_types import PythonRecordFallbackTestCase
from tests.unit.src.sqlbuild.compiler.lineage.helpers import (
    make_compiled_model,
    make_compiled_project,
    project_column_lineage,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonRecordFallbackTestCase(
            description="lineage over Python-built models reads them by attribute",
            expected_upstream_resource="orders",
            expected_fallbacks_counted=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_built_models_when_building_lineage_then_reads_fall_back_and_are_counted(
    test_case: PythonRecordFallbackTestCase,
) -> None:
    models: tuple[CompiledModelView, ...] = (
        make_compiled_model(
            name="orders", query_sql="SELECT 1 AS order_id", inferred_columns=("order_id",)
        ),
        make_compiled_model(
            name="orders_out",
            query_sql='SELECT order_id FROM __ref("orders")',
            inferred_columns=("order_id",),
        ),
    )
    _ = native.compile_stage_work_info(reset=True)
    lineage: ProjectColumnLineage | None = project_column_lineage(
        project=make_compiled_project(models=models)
    )
    fallbacks: int = native.compile_stage_work_info(reset=True).get("compiled_view_fallbacks", 0)

    assert lineage is not None
    upstream: str = lineage.models["orders_out"].columns[0].upstream_columns[0].resource_name
    assert (upstream, fallbacks > 0) == (
        test_case.expected_upstream_resource,
        test_case.expected_fallbacks_counted,
    )
