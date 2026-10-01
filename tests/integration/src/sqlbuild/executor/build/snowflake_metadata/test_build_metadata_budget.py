"""Build-time metadata budget for a Snowflake project, compiled, planned, and built offline.

Only the network is replaced: a simulated warehouse answers SHOW and INFORMATION_SCHEMA reads
from a catalog that follows the DDL the build itself issues.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.executor.build.snowflake_metadata._test_types import (
    BuildMetadataBudgetTestCase,
    SchemaEvolutionTestCase,
)
from tests.integration.src.sqlbuild.executor.build.snowflake_metadata.helpers import (
    ORDER_COLUMNS,
    OfflineBuild,
    SimulatedSnowflakeWarehouse,
    build_offline_snowflake_project,
    column_reads_by_relation,
    failed_models,
    information_schema_statements,
    orders_warehouse,
    repeated_metadata_reads,
    write_orders_project,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import FakeColumn

_FIRST_BUILD_COLUMN_READS: dict[str, int] = {
    "ANALYTICS.MARTS.ORDERS_TABLE__STAGING": 1,
    "ANALYTICS.MARTS.ORDERS_MERGE__STAGING": 1,
    "ANALYTICS.MARTS.ORDERS_DAILY__DELTA": 3,
    "ANALYTICS.MARTS.__SQB_REBUILD__ORDERS_DAILY": 1,
}
_SECOND_BUILD_COLUMN_READS: dict[str, int] = {
    "ANALYTICS.MARTS.ORDERS_TABLE__STAGING": 1,
    "ANALYTICS.MARTS.ORDERS_MERGE__DELTA": 1,
    "ANALYTICS.MARTS.ORDERS_MERGE": 1,
    "ANALYTICS.MARTS.ORDERS_DAILY__DELTA": 2,
    "ANALYTICS.MARTS.ORDERS_DAILY": 1,
}


@pytest.mark.parametrize(
    "test_case",
    [
        BuildMetadataBudgetTestCase(
            description="sequential workers",
            max_concurrency=1,
            expected_first_column_reads=_FIRST_BUILD_COLUMN_READS,
            expected_second_column_reads=_SECOND_BUILD_COLUMN_READS,
        ),
        BuildMetadataBudgetTestCase(
            description="concurrent workers",
            max_concurrency=4,
            expected_first_column_reads=_FIRST_BUILD_COLUMN_READS,
            expected_second_column_reads=_SECOND_BUILD_COLUMN_READS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_view_merge_and_microbatch_when_building_then_reads_each_relation_version_once(
    test_case: BuildMetadataBudgetTestCase, tmp_path: Path
) -> None:
    write_orders_project(project_dir=tmp_path)
    warehouse: SimulatedSnowflakeWarehouse = orders_warehouse()

    first: OfflineBuild = build_offline_snowflake_project(
        project_dir=tmp_path, warehouse=warehouse, max_concurrency=test_case.max_concurrency
    )
    second: OfflineBuild = build_offline_snowflake_project(
        project_dir=tmp_path, warehouse=warehouse, max_concurrency=test_case.max_concurrency
    )

    assert failed_models(first) == ()
    assert failed_models(second) == ()
    assert information_schema_statements(first) == ()
    assert information_schema_statements(second) == ()
    assert repeated_metadata_reads(first) == ()
    assert repeated_metadata_reads(second) == ()
    assert column_reads_by_relation(first) == test_case.expected_first_column_reads
    assert column_reads_by_relation(second) == test_case.expected_second_column_reads


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaEvolutionTestCase(
            description="appended delta column reaches the merge",
            added_column="NOTE",
            expected_target_reads=2,
            expected_merge_fragment='INSERT ("ORDER_ID", "ORDERED_AT", "AMOUNT", "NOTE")',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_delta_gains_column_when_building_then_merge_reads_altered_target_again(
    test_case: SchemaEvolutionTestCase, tmp_path: Path
) -> None:
    write_orders_project(project_dir=tmp_path)
    warehouse: SimulatedSnowflakeWarehouse = orders_warehouse()
    _ = build_offline_snowflake_project(
        project_dir=tmp_path, warehouse=warehouse, max_concurrency=1
    )
    warehouse.set_model_columns(
        model="ORDERS_MERGE",
        columns=(*ORDER_COLUMNS, FakeColumn(name=test_case.added_column, data_type="TEXT")),
    )

    evolved: OfflineBuild = build_offline_snowflake_project(
        project_dir=tmp_path, warehouse=warehouse, max_concurrency=1
    )

    merges: tuple[str, ...] = tuple(
        filter(lambda statement: statement.startswith("MERGE INTO"), evolved.statements)
    )
    assert failed_models(evolved) == ()
    assert repeated_metadata_reads(evolved) == ()
    assert (
        column_reads_by_relation(evolved)["ANALYTICS.MARTS.ORDERS_MERGE"]
        == test_case.expected_target_reads
    )
    assert len(merges) == 1
    assert test_case.expected_merge_fragment in merges[0]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
