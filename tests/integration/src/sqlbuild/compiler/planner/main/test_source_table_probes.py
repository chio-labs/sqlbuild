"""Planning reuses the source listing for S405 and probes only sources the listing missed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    SourceTableProbeBudgetTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    CountingSourceDuckDbAdapter,
    plan_source_reading_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceTableProbeBudgetTestCase(
            description="listed source table plans without extra listing or probe",
            source_schema="raw",
            source_table="orders",
            expected_source_listings=1,
            expected_probes=(),
        ),
        SourceTableProbeBudgetTestCase(
            description="case-variant source the listing misses is confirmed by one probe",
            source_schema="Raw",
            source_table="Orders",
            expected_source_listings=1,
            expected_probes=("Raw.Orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_source_table_when_planning_then_listing_is_reused(
    test_case: SourceTableProbeBudgetTestCase,
    tmp_path: Path,
    connection: Any,
) -> None:
    connection.execute("CREATE SCHEMA raw")
    connection.execute("CREATE TABLE raw.orders AS SELECT 1 AS order_id")
    counting: CountingSourceDuckDbAdapter = CountingSourceDuckDbAdapter(connection=connection)

    result: CompilePipelineResult = plan_source_reading_project(
        project_dir=tmp_path,
        adapter=counting,
        source_schema=test_case.source_schema,
        source_table=test_case.source_table,
    )

    assert [entry.name for entry in result.plan_output.model_entries] == ["orders"]
    assert (
        sum("raw" in schemas for schemas in counting.listed_schema_sets)
        == test_case.expected_source_listings
    )
    assert tuple(counting.probed_relations) == test_case.expected_probes


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
