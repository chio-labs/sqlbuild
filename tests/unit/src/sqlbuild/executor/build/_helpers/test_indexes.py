from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.build._helpers.indexes import build_execution_indexes
from sqlbuild.executor.build.models import BuildIndexes
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    AuditExecutionIndexTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AuditExecutionIndexTestCase(
            description="end-scheduled model audit is indexed exactly once at end",
            expected_model_audit_count=0,
            expected_end_audit_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_end_scheduled_model_audit_when_building_indexes_then_it_is_not_a_model_gate(
    test_case: AuditExecutionIndexTestCase,
) -> None:
    audit: AuditPlanEntry = AuditPlanEntry(
        key=CompiledObjectKey(CompiledResourceType.AUDIT, "cross_model_consistency"),
        name="cross_model_consistency",
        definition_name="test_audit",
        resolved_sql="SELECT 1 WHERE FALSE",
        unresolved_sql="SELECT 1 WHERE FALSE",
        attachment_kind=AuditAttachmentKind.END,
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
        severity=AuditSeverity.ERROR,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
    )

    indexes: BuildIndexes = build_execution_indexes(PlanOutput(audit_entries=(audit,)))

    assert sum(len(audits) for audits in indexes.model_audits_by_model.values()) == (
        test_case.expected_model_audit_count
    )
    assert len(indexes.end_audits) == test_case.expected_end_audit_count
    assert indexes.end_audits[0].attached_target_name == "orders"
