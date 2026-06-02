"""Integration tests for audit SQL rendering executed against DuckDB."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.auditing.main.render import render_audit_sql
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.spec.models.source import SourceEntry
from tests.integration.src.sqlbuild.compiler.auditing.main._test_types import (
    ExecuteRenderedAuditTestCase,
)

EXECUTE_RENDERED_AUDIT_TEST_CASES: list[ExecuteRenderedAuditTestCase] = [
    ExecuteRenderedAuditTestCase(
        description="override directs audit to staging table with nulls instead of clean final",
        setup_sql=(
            "CREATE TABLE main.orders (id INTEGER NOT NULL, name VARCHAR NOT NULL)",
            "INSERT INTO main.orders VALUES (1, 'alice'), (2, 'bob')",
            "CREATE TABLE main.orders__staging (id INTEGER, name VARCHAR)",
            "INSERT INTO main.orders__staging VALUES (1, 'alice'), (NULL, 'bob'), (NULL, NULL)",
        ),
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        model_targets={"orders": "main.orders"},
        relation_overrides={"orders": "main.orders__staging"},
        source_map={},
        expected_row_count=2,
    ),
    ExecuteRenderedAuditTestCase(
        description="no override executes against clean final table",
        setup_sql=(
            "CREATE TABLE main.orders (id INTEGER NOT NULL, name VARCHAR NOT NULL)",
            "INSERT INTO main.orders VALUES (1, 'alice'), (2, 'bob')",
        ),
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        model_targets={"orders": "main.orders"},
        source_map={},
        expected_row_count=0,
    ),
    ExecuteRenderedAuditTestCase(
        description="source render executes against source table",
        setup_sql=(
            "CREATE TABLE main.raw_orders (id INTEGER, status VARCHAR)",
            "INSERT INTO main.raw_orders VALUES (1, 'paid'), (2, NULL), (3, NULL)",
        ),
        unresolved_sql='SELECT id FROM __source("raw_orders") WHERE status IS NULL',
        model_targets={},
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                schema="main",
                table="raw_orders",
            ),
        },
        expected_row_count=2,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXECUTE_RENDERED_AUDIT_TEST_CASES,
    ids=[case.description for case in EXECUTE_RENDERED_AUDIT_TEST_CASES],
)
def test_given_rendered_audit_sql_when_executing_then_returns_expected_rows(
    test_case: ExecuteRenderedAuditTestCase,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    model_targets: dict[str, CompiledRelationDestination] = {
        name: CompiledRelationDestination(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in test_case.model_targets.items()
    }

    rendered_sql: str = render_audit_sql(
        unresolved_sql=test_case.unresolved_sql,
        model_targets=model_targets,
        seed_targets={},
        source_map=test_case.source_map,
        relation_overrides=test_case.relation_overrides if test_case.relation_overrides else None,
    )

    query_result: Any = connection.execute(rendered_sql)
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
