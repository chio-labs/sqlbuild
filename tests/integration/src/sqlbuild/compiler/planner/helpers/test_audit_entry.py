from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
)
from sqlbuild.compiler.planner.helpers.audit_entry import plan_audit
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.spec.models.source import SourceEntry
from tests.integration.src.sqlbuild.compiler.planner.helpers._test_types import (
    ExecuteAuditTestCase,
)

_STUB_FILE: DiscoveredAuditFile = DiscoveredAuditFile(
    file_path=Path("audits/generic/not_null.sql"),
    relative_path=Path("audits/generic/not_null.sql"),
    contents="",
    blocks=(),
)

_STUB_BLOCK: DiscoveredAuditBlock = DiscoveredAuditBlock(
    audit_index=0,
    header_values={},
    sql_body="",
)

EXECUTE_AUDIT_TEST_CASES: list[ExecuteAuditTestCase] = [
    ExecuteAuditTestCase(
        description=("not_null audit on clean table returns zero rows"),
        setup_sql=(
            "CREATE TABLE main.orders (id INTEGER NOT NULL, name VARCHAR NOT NULL)",
            "INSERT INTO main.orders VALUES (1, 'alice'), (2, 'bob')",
        ),
        audit_sql=('SELECT id FROM __ref("orders") WHERE id IS NULL'),
        model_targets={"orders": "main.orders"},
        source_map={},
        expected_row_count=0,
    ),
    ExecuteAuditTestCase(
        description=("not_null audit on table with nulls returns failing rows"),
        setup_sql=(
            "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
            "INSERT INTO main.orders VALUES (1, 'alice'), (NULL, 'bob'), (NULL, NULL)",
        ),
        audit_sql=('SELECT id FROM __ref("orders") WHERE id IS NULL'),
        model_targets={"orders": "main.orders"},
        source_map={},
        expected_row_count=2,
    ),
    ExecuteAuditTestCase(
        description=("audit with source reference executes against source table"),
        setup_sql=(
            "CREATE TABLE main.raw_payments (id INTEGER, status VARCHAR)",
            "INSERT INTO main.raw_payments VALUES (1, 'paid'), (2, NULL)",
        ),
        audit_sql=('SELECT id FROM __source("raw_payments") WHERE status IS NULL'),
        model_targets={},
        source_map={
            "raw_payments": SourceEntry(
                name="raw_payments",
                schema="main",
                table="raw_payments",
            ),
        },
        expected_row_count=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXECUTE_AUDIT_TEST_CASES,
    ids=[case.description for case in EXECUTE_AUDIT_TEST_CASES],
)
def test_given_audit_when_executing_resolved_sql_then_returns_expected_rows(
    test_case: ExecuteAuditTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    audit: CompiledAudit = CompiledAudit(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.AUDIT,
            name="test_audit",
        ),
        scope_deps=(),
        name="test_audit",
        audit_file=_STUB_FILE,
        audit_block=_STUB_BLOCK,
        sql_body=test_case.audit_sql,
    )

    model_targets: dict[str, CompiledRelationTarget] = {
        name: CompiledRelationTarget(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in test_case.model_targets.items()
    }

    result: AuditPlanEntry = plan_audit(
        audit=audit,
        model_targets=model_targets,
        seed_targets={},
        source_map=test_case.source_map,
        upstream_deps={},
        downstream_deps={},
        model_materializations={},
    )

    query_result: Any = connection.execute(result.resolved_sql)
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
