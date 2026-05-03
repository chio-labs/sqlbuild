from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.helpers.strategy import build_logical_ddl
from sqlbuild.compiler.planner.types import PlanAction
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    BuildLogicalDdlTestCase,
)

_SIMPLE_SQL: str = "SELECT id, name FROM raw_orders"

_WAREHOUSE_COLUMNS: tuple[ColumnInfo, ...] = (
    ColumnInfo(name="order_id", type="INTEGER"),
    ColumnInfo(name="name", type="VARCHAR"),
    ColumnInfo(name="amount", type="DECIMAL"),
)

BUILD_DDL_TEST_CASES: list[BuildLogicalDdlTestCase] = [
    BuildLogicalDdlTestCase(
        description="create view wraps sql in create or replace view",
        action=PlanAction.CREATE_VIEW,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="CREATE OR REPLACE VIEW staging.orders AS",
    ),
    BuildLogicalDdlTestCase(
        description="create table wraps sql in create table as",
        action=PlanAction.CREATE_TABLE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="CREATE TABLE staging.orders AS",
    ),
    BuildLogicalDdlTestCase(
        description="incremental append wraps sql in insert into",
        action=PlanAction.INCREMENTAL_APPEND,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="INSERT INTO staging.orders",
    ),
    BuildLogicalDdlTestCase(
        description="delete_insert produces delete and insert statements",
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=(),
        expected_ddl_fragment="DELETE FROM staging.orders",
    ),
    BuildLogicalDdlTestCase(
        description="delete_insert includes unique key in where clause",
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=(),
        expected_ddl_fragment="WHERE (order_id) IN",
    ),
    BuildLogicalDdlTestCase(
        description="merge produces merge into with on clause",
        action=PlanAction.INCREMENTAL_MERGE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=_WAREHOUSE_COLUMNS,
        expected_ddl_fragment="MERGE INTO staging.orders AS target",
    ),
    BuildLogicalDdlTestCase(
        description="merge includes update set for non-key columns",
        action=PlanAction.INCREMENTAL_MERGE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=_WAREHOUSE_COLUMNS,
        expected_ddl_fragment=(
            "WHEN MATCHED THEN UPDATE SET name = __source.name, amount = __source.amount"
        ),
    ),
    BuildLogicalDdlTestCase(
        description="merge includes insert clause with all columns",
        action=PlanAction.INCREMENTAL_MERGE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=_WAREHOUSE_COLUMNS,
        expected_ddl_fragment="WHEN NOT MATCHED THEN INSERT (order_id, name, amount)",
    ),
    BuildLogicalDdlTestCase(
        description="merge on clause uses unique key",
        action=PlanAction.INCREMENTAL_MERGE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id",),
        warehouse_columns=_WAREHOUSE_COLUMNS,
        expected_ddl_fragment="ON target.order_id = __source.order_id",
    ),
    BuildLogicalDdlTestCase(
        description="skip action produces empty ddl",
        action=PlanAction.SKIP,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="",
    ),
    BuildLogicalDdlTestCase(
        description="create view includes resolved sql in body",
        action=PlanAction.CREATE_VIEW,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment=_SIMPLE_SQL,
    ),
    BuildLogicalDdlTestCase(
        description="delete_insert with composite key uses both columns",
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id", "line_id"),
        warehouse_columns=(),
        expected_ddl_fragment="WHERE (order_id, line_id) IN",
    ),
    BuildLogicalDdlTestCase(
        description="load_seed action produces empty ddl",
        action=PlanAction.LOAD_SEED,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="",
    ),
    BuildLogicalDdlTestCase(
        description="merge with composite key joins on both columns",
        action=PlanAction.INCREMENTAL_MERGE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name="staging.orders",
        unique_key=("order_id", "line_id"),
        warehouse_columns=_WAREHOUSE_COLUMNS,
        expected_ddl_fragment=(
            "ON target.order_id = __source.order_id AND target.line_id = __source.line_id"
        ),
    ),
    BuildLogicalDdlTestCase(
        description=("falls back to target name when qualified name is none"),
        action=PlanAction.CREATE_TABLE,
        resolved_sql=_SIMPLE_SQL,
        qualified_name=None,
        unique_key=(),
        warehouse_columns=(),
        expected_ddl_fragment="CREATE TABLE orders AS",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_DDL_TEST_CASES,
    ids=[case.description for case in BUILD_DDL_TEST_CASES],
)
def test_given_action_and_sql_when_building_ddl_then_contains_expected_fragment(
    test_case: BuildLogicalDdlTestCase,
) -> None:
    target: CompiledRelationTarget = CompiledRelationTarget(
        database=None,
        schema="staging",
        name="orders",
        qualified_name=test_case.qualified_name,
    )

    result: str = build_logical_ddl(
        action=test_case.action,
        resolved_sql=test_case.resolved_sql,
        target=target,
        unique_key=test_case.unique_key,
        warehouse_columns=test_case.warehouse_columns,
    )

    assert test_case.expected_ddl_fragment in result
