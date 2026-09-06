"""Tests for audit result warehouse SQL builders."""

import pytest

from sqlbuild.executor.audit_results._helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
)
from sqlbuild.executor.audit_results.constants import (
    AUDIT_RESULT_COLUMN_TYPES,
    AUDIT_RESULT_COLUMNS,
)
from tests.unit.src.sqlbuild.executor.audit_results._helpers._test_types import (
    AuditResultSqlTestCase,
)
from tests.unit.src.sqlbuild.executor.audit_results._helpers.helpers import (
    build_record,
    render_framework_type,
    render_qualified_name,
)
from tests.unit.src.sqlbuild.executor.audit_results._helpers.test_goldens import (
    CREATE_TABLE_SQL_GOLDEN,
    INSERT_SQL_GOLDEN,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultSqlTestCase(
            description="all columns typed",
            expected_sql=",".join(AUDIT_RESULT_COLUMNS),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_audit_result_columns_when_checking_types_then_every_column_is_declared(
    test_case: AuditResultSqlTestCase,
) -> None:
    assert ",".join(AUDIT_RESULT_COLUMN_TYPES) == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultSqlTestCase(
            description="create table golden",
            expected_sql=CREATE_TABLE_SQL_GOLDEN,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_audit_result_schema_when_building_create_sql_then_matches_golden(
    test_case: AuditResultSqlTestCase,
) -> None:
    sql: str = build_create_table_sql(
        database=None,
        schema="analytics",
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
    )

    assert sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultSqlTestCase(
            description="multi-row insert golden",
            expected_sql=INSERT_SQL_GOLDEN,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_multiple_records_when_building_insert_sql_then_matches_golden(
    test_case: AuditResultSqlTestCase,
) -> None:
    sql: str = build_insert_sql(
        database=None,
        schema="analytics",
        records=(
            build_record(result_id="result-1", measured_value=99.25),
            build_record(result_id="result-2", measured_value=None),
        ),
        render_qualified_name=render_qualified_name,
    )

    assert sql == test_case.expected_sql
