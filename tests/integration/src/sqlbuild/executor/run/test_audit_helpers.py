"""Tests for table executor audit helper assembly."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import AuditPlanEntry
from tests.integration.src.sqlbuild.executor.run._test_types import AuditSqlResolutionTestCase
from tests.integration.src.sqlbuild.executor.run.helpers import build_test_audit_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        AuditSqlResolutionTestCase(
            description="resolves logical ref to schema-qualified table target",
            unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
            attached_target_name="orders",
            resolved_target_name="staging.orders",
            expected_resolved_sql="SELECT id FROM staging.orders WHERE id IS NULL",
        )
    ],
    ids=["resolves logical ref to schema-qualified table target"],
)
def test_given_manual_audit_entry_when_building_then_resolved_sql_uses_qualified_target(
    test_case: AuditSqlResolutionTestCase,
) -> None:
    entry: AuditPlanEntry = build_test_audit_plan_entry(
        name="not_null",
        unresolved_sql=test_case.unresolved_sql,
        attached_target_name=test_case.attached_target_name,
        resolved_target_name=test_case.resolved_target_name,
    )

    assert entry.resolved_sql == test_case.expected_resolved_sql
    assert "__ref(" not in entry.resolved_sql
    assert entry.unresolved_sql == test_case.unresolved_sql
