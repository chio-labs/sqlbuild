"""Tests for audit gate identity hashing."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.main.identity import build_audit_gate_identity
from sqlbuild.compiler.auditing.models import AuditGateIdentity
from sqlbuild.compiler.auditing.types import AuditAttachmentKind, AuditRunScope, AuditSeverity
from sqlbuild.compiler.planner.models import AuditPlanEntry
from tests.unit.src.sqlbuild.compiler.auditing.main._test_types import (
    AuditGateAggregateIdentityTestCase,
    AuditGateIdentityTestCase,
    AuditGateSingleFieldIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.auditing.main.helpers import build_audit_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateIdentityTestCase(
            description="definition ignores target-specific relation names",
            unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            prod_resolved_sql="SELECT order_id FROM prod.orders WHERE order_id IS NULL",
            dev_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            expected_definition_equal=True,
            expected_execution_equal=False,
            expected_binding_set_equal=True,
        ),
        AuditGateIdentityTestCase(
            description="binding changes alter binding set hash",
            unresolved_sql='SELECT status FROM __ref("orders") WHERE status IS NULL',
            prod_resolved_sql="SELECT status FROM prod.orders WHERE status IS NULL",
            dev_resolved_sql="SELECT status FROM prod.orders WHERE status IS NULL",
            dev_attached_column_name="status",
            expected_definition_equal=False,
            expected_execution_equal=False,
            expected_binding_set_equal=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_plan_entries_when_building_identity_then_hashes_expected_fields(
    test_case: AuditGateIdentityTestCase,
) -> None:
    prod_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql=test_case.unresolved_sql,
        resolved_sql=test_case.prod_resolved_sql,
        severity=test_case.severity,
    )
    dev_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql=test_case.unresolved_sql,
        resolved_sql=test_case.dev_resolved_sql,
        attached_column_name=test_case.dev_attached_column_name,
        severity=test_case.severity,
    )

    prod_identity: AuditGateIdentity = build_audit_gate_identity(audits=(prod_audit,))
    dev_identity: AuditGateIdentity = build_audit_gate_identity(audits=(dev_audit,))

    assert (
        prod_identity.audits[0].definition_fingerprint
        == dev_identity.audits[0].definition_fingerprint
    ) is test_case.expected_definition_equal
    assert (
        prod_identity.audits[0].execution_fingerprint
        == dev_identity.audits[0].execution_fingerprint
    ) is test_case.expected_execution_equal
    assert (
        prod_identity.binding_set_hash == dev_identity.binding_set_hash
    ) is test_case.expected_binding_set_equal


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateAggregateIdentityTestCase(
            description="audit order does not affect aggregate hashes",
            expected_binding_set_equal=True,
            expected_blocking_set_equal=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_audits_in_different_order_when_building_identity_then_aggregate_hashes_match(
    test_case: AuditGateAggregateIdentityTestCase,
) -> None:
    first_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
        resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
    )
    second_audit: AuditPlanEntry = build_audit_plan_entry(
        name="accepted_status",
        unresolved_sql="SELECT status FROM __ref(\"orders\") WHERE status NOT IN ('placed')",
        resolved_sql="SELECT status FROM dev.orders WHERE status NOT IN ('placed')",
    )

    left_identity: AuditGateIdentity = build_audit_gate_identity(audits=(first_audit, second_audit))
    right_identity: AuditGateIdentity = build_audit_gate_identity(
        audits=(second_audit, first_audit)
    )

    assert (
        left_identity.binding_set_hash == right_identity.binding_set_hash
    ) is test_case.expected_binding_set_equal
    assert (
        left_identity.blocking_set_hash == right_identity.blocking_set_hash
    ) is test_case.expected_blocking_set_equal


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateAggregateIdentityTestCase(
            description="warn audits do not affect blocking hash",
            expected_binding_set_equal=False,
            expected_blocking_set_equal=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_warn_audit_changes_when_building_identity_then_blocking_hash_is_unchanged(
    test_case: AuditGateAggregateIdentityTestCase,
) -> None:
    error_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
        resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
        severity=AuditSeverity.ERROR,
    )
    warn_audit: AuditPlanEntry = build_audit_plan_entry(
        name="warn_recent_orders",
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_date < CURRENT_DATE',
        resolved_sql="SELECT order_id FROM dev.orders WHERE order_date < CURRENT_DATE",
        severity=AuditSeverity.WARN,
    )

    error_only_identity: AuditGateIdentity = build_audit_gate_identity(audits=(error_audit,))
    with_warn_identity: AuditGateIdentity = build_audit_gate_identity(
        audits=(error_audit, warn_audit)
    )

    assert (
        error_only_identity.binding_set_hash == with_warn_identity.binding_set_hash
    ) is test_case.expected_binding_set_equal
    assert (
        error_only_identity.blocking_set_hash == with_warn_identity.blocking_set_hash
    ) is test_case.expected_blocking_set_equal


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateSingleFieldIdentityTestCase(
            description="sql whitespace is normalized",
            left_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            left_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            right_unresolved_sql=(
                '  SELECT   order_id\nFROM   __ref("orders")\nWHERE   order_id   IS NULL  '
            ),
            right_resolved_sql=(
                "  SELECT   order_id\nFROM   dev.orders\nWHERE   order_id   IS NULL  "
            ),
            expected_definition_equal=True,
            expected_execution_equal=True,
        ),
        AuditGateSingleFieldIdentityTestCase(
            description="run scope changes identity",
            left_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            left_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            right_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            right_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            left_run_scope=AuditRunScope.FINAL,
            right_run_scope=AuditRunScope.DELTA_AND_FINAL,
            expected_definition_equal=False,
            expected_execution_equal=False,
        ),
        AuditGateSingleFieldIdentityTestCase(
            description="attachment kind changes identity",
            left_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            left_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            right_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            right_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            left_attachment_kind=AuditAttachmentKind.MODEL,
            right_attachment_kind=AuditAttachmentKind.END,
            expected_definition_equal=False,
            expected_execution_equal=False,
        ),
        AuditGateSingleFieldIdentityTestCase(
            description="always_run changes identity",
            left_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            left_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            right_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            right_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            left_always_run=False,
            right_always_run=True,
            expected_definition_equal=False,
            expected_execution_equal=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_single_audit_field_difference_when_building_identity_then_hashes_expected_fields(
    test_case: AuditGateSingleFieldIdentityTestCase,
) -> None:
    left_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql=test_case.left_unresolved_sql,
        resolved_sql=test_case.left_resolved_sql,
        effective_run_scope=test_case.left_run_scope,
        attachment_kind=test_case.left_attachment_kind,
        always_run=test_case.left_always_run,
    )
    right_audit: AuditPlanEntry = build_audit_plan_entry(
        name="not_null_orders",
        unresolved_sql=test_case.right_unresolved_sql,
        resolved_sql=test_case.right_resolved_sql,
        effective_run_scope=test_case.right_run_scope,
        attachment_kind=test_case.right_attachment_kind,
        always_run=test_case.right_always_run,
    )

    left_identity: AuditGateIdentity = build_audit_gate_identity(audits=(left_audit,))
    right_identity: AuditGateIdentity = build_audit_gate_identity(audits=(right_audit,))

    assert (
        left_identity.audits[0].definition_fingerprint
        == right_identity.audits[0].definition_fingerprint
    ) is test_case.expected_definition_equal
    assert (
        left_identity.audits[0].execution_fingerprint
        == right_identity.audits[0].execution_fingerprint
    ) is test_case.expected_execution_equal
