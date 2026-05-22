"""Tests for view executor audit helper assembly."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import AuditPlanEntry
from tests.integration.src.sqlbuild.executor.run.view._test_types import (
    ViewAuditSqlResolutionTestCase,
)
from tests.integration.src.sqlbuild.executor.run.view.helpers import build_view_audit_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        ViewAuditSqlResolutionTestCase(
            description="resolves logical ref to schema-qualified view target",
            unresolved_sql='SELECT id FROM __ref("dim_view") WHERE id IS NULL',
            attached_target_name="dim_view",
            resolved_target_name="test_schema.dim_customers",
            expected_resolved_sql="SELECT id FROM test_schema.dim_customers WHERE id IS NULL",
        )
    ],
    ids=["resolves logical ref to schema-qualified view target"],
)
def test_given_manual_view_audit_entry_when_building_then_resolved_sql_uses_qualified_target(
    test_case: ViewAuditSqlResolutionTestCase,
) -> None:
    entry: AuditPlanEntry = build_view_audit_plan_entry(
        name="not_null",
        unresolved_sql=test_case.unresolved_sql,
        attached_target_name=test_case.attached_target_name,
        resolved_target_name=test_case.resolved_target_name,
    )

    assert entry.resolved_sql == test_case.expected_resolved_sql
    assert "__ref(" not in entry.resolved_sql
    assert entry.unresolved_sql == test_case.unresolved_sql
