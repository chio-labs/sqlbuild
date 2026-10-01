"""Round-trip budget guard for planning a large multi-schema Snowflake project offline.

The project is compiled and planned through the real pipeline; only the network is replaced by
a recording warehouse that answers metadata SQL from in-memory synthetic catalog rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.relations.constants import INSPECTION_IN_LIST_LIMIT
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    SnowflakeCursorBoundsBudgetTestCase,
    SnowflakeInspectionBudgetTestCase,
    SnowflakeReplanTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    offline_cursor_bound_relations,
    offline_metadata_queries,
    offline_metadata_reads_by_schema,
    plan_offline_snowflake_project,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    OfflineSnowflakeAdapter,
    RecordedQuery,
    RecordingSnowflakeWarehouse,
    SyntheticSnowflakeProject,
    write_synthetic_snowflake_project,
)

_ONE_READ_PER_SCHEMA: dict[str, int] = {"STAGING": 1, "INTERMEDIATE": 1, "MARTS": 1, "RAW": 1}


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeInspectionBudgetTestCase(
            description="about 2,500 relations",
            unmanaged_relations_per_schema=450,
            expected_schema_reads=_ONE_READ_PER_SCHEMA,
            expected_metadata_budget=8,
            expected_in_list_limit=INSPECTION_IN_LIST_LIMIT,
        ),
        SnowflakeInspectionBudgetTestCase(
            description="about 4,300 relations",
            unmanaged_relations_per_schema=900,
            expected_schema_reads=_ONE_READ_PER_SCHEMA,
            expected_metadata_budget=8,
            expected_in_list_limit=INSPECTION_IN_LIST_LIMIT,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_multi_schema_project_when_planning_then_metadata_reads_stay_in_budget(
    test_case: SnowflakeInspectionBudgetTestCase, tmp_path: Path
) -> None:
    project: SyntheticSnowflakeProject = write_synthetic_snowflake_project(
        project_dir=tmp_path / "orders_platform",
        models_per_schema=60,
        incremental_every=2,
        sources=260,
        unmanaged_relations_per_schema=test_case.unmanaged_relations_per_schema,
    )
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=project.relations
    )

    result: CompilePipelineResult = plan_offline_snowflake_project(
        project=project, warehouse=warehouse
    )

    metadata: tuple[RecordedQuery, ...] = offline_metadata_queries(warehouse)
    assert len(result.plan_output.model_entries) == len(project.model_schemas)
    assert (
        offline_metadata_reads_by_schema(warehouse=warehouse, kind="tables")
        == test_case.expected_schema_reads
    )
    assert (
        offline_metadata_reads_by_schema(warehouse=warehouse, kind="columns")
        == test_case.expected_schema_reads
    )
    assert warehouse.queries_of_kind("show_columns") == ()
    assert warehouse.queries_of_kind("other_metadata") == ()
    assert max(query.largest_in_list for query in metadata) <= test_case.expected_in_list_limit
    assert len({(query.sql, query.params) for query in metadata}) == len(metadata)
    assert len(metadata) <= test_case.expected_metadata_budget


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCursorBoundsBudgetTestCase(
            description="one statement per relation with bounded parallelism",
            statement_latency_seconds=0.002,
            expected_max_concurrency=OfflineSnowflakeAdapter.metadata_inspection_concurrency,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_models_when_planning_then_cursor_bounds_run_one_per_relation_in_parallel(
    test_case: SnowflakeCursorBoundsBudgetTestCase, tmp_path: Path
) -> None:
    project: SyntheticSnowflakeProject = write_synthetic_snowflake_project(
        project_dir=tmp_path / "orders_platform",
        models_per_schema=60,
        incremental_every=2,
        unmanaged_relations_per_schema=50,
    )
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=project.relations, statement_latency_seconds=test_case.statement_latency_seconds
    )

    _ = plan_offline_snowflake_project(project=project, warehouse=warehouse)

    bounds: tuple[RecordedQuery, ...] = warehouse.queries_of_kind("cursor_bounds")
    relations: tuple[str, ...] = offline_cursor_bound_relations(warehouse)
    assert len(bounds) >= len(project.incremental_model_names)
    assert all("UNION" not in query.sql.upper() for query in bounds)
    assert len(relations) == len(bounds) == len(set(relations))
    assert 1 < warehouse.max_concurrent_cursor_bounds <= test_case.expected_max_concurrency


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeReplanTestCase(
            description="a second invocation re-reads bounds and listings", expected_tables_reads=4
        )
    ],
    ids=lambda case: case.description,
)
def test_given_planned_project_when_planning_again_then_cursor_bounds_are_read_again(
    test_case: SnowflakeReplanTestCase, tmp_path: Path
) -> None:
    project: SyntheticSnowflakeProject = write_synthetic_snowflake_project(
        project_dir=tmp_path / "orders_platform", unmanaged_relations_per_schema=10
    )
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=project.relations
    )
    _ = plan_offline_snowflake_project(project=project, warehouse=warehouse)
    first: int = len(warehouse.queries_of_kind("cursor_bounds"))
    warehouse.reset()

    _ = plan_offline_snowflake_project(project=project, warehouse=warehouse, no_cache=False)

    assert len(warehouse.queries_of_kind("cursor_bounds")) == first
    assert len(warehouse.queries_of_kind("tables")) == test_case.expected_tables_reads


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
