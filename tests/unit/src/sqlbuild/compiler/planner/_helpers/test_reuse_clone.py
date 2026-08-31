"""Tests for clone and reuse model plan-entry construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.reuse.clone import (
    build_clone_model_entries,
    build_origin_model_entries,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ClonePermanentTableTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClonePermanentTableTestCase(
            description="omitted declaration remains transient",
            config_values={"materialized": "table"},
            expected_permanent_table=False,
        ),
        ClonePermanentTableTestCase(
            description="permanent declaration survives clone and reuse planning",
            config_values={"materialized": "table", "table_type": "permanent"},
            expected_permanent_table=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_type_declaration_when_building_clone_entries_then_table_kind_is_preserved(
    test_case: ClonePermanentTableTestCase,
) -> None:
    key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    model: CompiledModel = CompiledModel(
        key=key,
        deps=(),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="SELECT 1 AS id",
        config=CompileModelConfig(values=test_case.config_values),
        destination=CompiledRelationLocation(
            database=None,
            schema="public",
            name="orders",
            qualified_name="public.orders",
        ),
    )
    project: CompiledProject = CompiledProject(
        run_id="test",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=(model,),
    )
    plan: PlanOutput = PlanOutput(
        execution_order=(key,),
        selected_keys=frozenset((key,)),
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        destination_entries: tuple[ModelPlanEntry, ...] = build_clone_model_entries(
            project=project,
            plan=plan,
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)
    origin_entries: tuple[ModelPlanEntry, ...] = build_origin_model_entries(
        project=project,
        selected_names=frozenset(("orders",)),
    )

    assert destination_entries[0].permanent_table is test_case.expected_permanent_table
    assert origin_entries[0].permanent_table is test_case.expected_permanent_table


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
