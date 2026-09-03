"""Tests for audit attachment resolution and scheduling validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
)
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledObjectKey,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
)
from sqlbuild.compiler.planner._helpers.output.audit_scheduling import (
    resolve_attachment_kind,
    resolve_effective_run_scope,
)
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.compiler.references.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ResolveAttachmentErrorTestCase,
    ResolveAttachmentTestCase,
    ResolveEffectiveRunScopeTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_scheduling_audit,
    build_scheduling_graph,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveAttachmentTestCase(
            description="source-attached audit returns SOURCE",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),
            ),
            attached_target_kind=AttachedAuditTargetKind.SOURCE,
            attached_target_name="raw_orders",
            upstream_edges={},
            expected_attachment_kind=AuditAttachmentKind.SOURCE,
            expected_attached_name="raw_orders",
        ),
        ResolveAttachmentTestCase(
            description="source-attached audit with seed dependency moves to END",
            references=(
                CompileSqlReference(
                    ref_kind=SqlReferenceKind.SOURCE,
                    ref_name="raw_orders",
                ),
                CompileSqlReference(
                    ref_kind=SqlReferenceKind.SEED,
                    ref_name="valid_order_statuses",
                ),
            ),
            attached_target_kind=AttachedAuditTargetKind.SOURCE,
            attached_target_name="raw_orders",
            upstream_edges={},
            expected_attachment_kind=AuditAttachmentKind.END,
            expected_attached_name="raw_orders",
        ),
        ResolveAttachmentTestCase(
            description="model-attached audit with upstream refs returns MODEL",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
            ),
            attached_target_kind=AttachedAuditTargetKind.MODEL,
            attached_target_name="orders",
            upstream_edges={"orders": ("stg_orders",), "stg_orders": ()},
            expected_attachment_kind=AuditAttachmentKind.MODEL,
            expected_attached_name="orders",
        ),
        ResolveAttachmentTestCase(
            description="model-attached audit with downstream ref moves to END",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
            ),
            attached_target_kind=AttachedAuditTargetKind.MODEL,
            attached_target_name="stg_orders",
            upstream_edges={"orders": ("stg_orders",), "stg_orders": ()},
            expected_attachment_kind=AuditAttachmentKind.END,
            expected_attached_name="stg_orders",
        ),
        ResolveAttachmentTestCase(
            description="model-attached audit with unrelated ref moves to END",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="customers"),
            ),
            attached_target_kind=AttachedAuditTargetKind.MODEL,
            attached_target_name="orders",
            upstream_edges={"orders": (), "customers": ()},
            expected_attachment_kind=AuditAttachmentKind.END,
            expected_attached_name="orders",
        ),
        ResolveAttachmentTestCase(
            description="singular audit with only source refs returns SOURCE",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),
            ),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={},
            expected_attachment_kind=AuditAttachmentKind.SOURCE,
            expected_attached_name="raw_orders",
        ),
        ResolveAttachmentTestCase(
            description="singular audit with single model ref returns MODEL",
            references=(CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={"orders": ()},
            expected_attachment_kind=AuditAttachmentKind.MODEL,
            expected_attached_name="orders",
        ),
        ResolveAttachmentTestCase(
            description="singular audit with chain A->B attaches to B as latest",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg_orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
            ),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={"orders": ("stg_orders",), "stg_orders": ()},
            expected_attachment_kind=AuditAttachmentKind.MODEL,
            expected_attached_name="orders",
        ),
        ResolveAttachmentTestCase(
            description="singular audit with unrelated models attaches to END",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="customers"),
            ),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={"orders": (), "customers": ()},
            expected_attachment_kind=AuditAttachmentKind.END,
            expected_attached_name=None,
        ),
        ResolveAttachmentTestCase(
            description="singular audit with no refs attaches to END",
            references=(),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={},
            expected_attachment_kind=AuditAttachmentKind.END,
            expected_attached_name=None,
        ),
        ResolveAttachmentTestCase(
            description="singular audit with three-model chain attaches to deepest",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="raw"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="stg"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="mart"),
            ),
            attached_target_kind=None,
            attached_target_name=None,
            upstream_edges={"mart": ("stg",), "stg": ("raw",), "raw": ()},
            expected_attachment_kind=AuditAttachmentKind.MODEL,
            expected_attached_name="mart",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_refs_when_resolving_attachment_then_returns_expected(
    test_case: ResolveAttachmentTestCase,
) -> None:
    audit: CompiledAudit = build_scheduling_audit(
        references=test_case.references,
        attached_target_kind=test_case.attached_target_kind,
        attached_target_name=test_case.attached_target_name,
    )
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    upstream, downstream = build_scheduling_graph(test_case.upstream_edges)

    kind: AuditAttachmentKind
    name: str | None
    kind, name = resolve_attachment_kind(
        audit=audit,
        upstream_deps=upstream,
        downstream_deps=downstream,
    )

    assert kind == test_case.expected_attachment_kind
    assert name == test_case.expected_attached_name


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveAttachmentErrorTestCase(
            description="source-attached audit referencing model raises",
            references=(
                CompileSqlReference(ref_kind=SqlReferenceKind.SOURCE, ref_name="raw_orders"),
                CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),
            ),
            attached_target_kind=AttachedAuditTargetKind.SOURCE,
            attached_target_name="raw_orders",
            upstream_edges={"orders": ()},
            expected_error_fragment="must not reference models",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_attachment_when_resolving_then_raises(
    test_case: ResolveAttachmentErrorTestCase,
) -> None:
    audit: CompiledAudit = build_scheduling_audit(
        references=test_case.references,
        attached_target_kind=test_case.attached_target_kind,
        attached_target_name=test_case.attached_target_name,
    )
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    upstream, downstream = build_scheduling_graph(test_case.upstream_edges)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        resolve_attachment_kind(
            audit=audit,
            upstream_deps=upstream,
            downstream_deps=downstream,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveEffectiveRunScopeTestCase(
            description="final requested stays final for incremental model",
            requested_run_scope=AuditRunScope.FINAL,
            attached_model_materialization=MaterializationType.INCREMENTAL,
            expected_effective_run_scope=AuditRunScope.FINAL,
        ),
        ResolveEffectiveRunScopeTestCase(
            description="delta_and_final on incremental model stays delta_and_final",
            requested_run_scope=AuditRunScope.DELTA_AND_FINAL,
            attached_model_materialization=MaterializationType.INCREMENTAL,
            expected_effective_run_scope=AuditRunScope.DELTA_AND_FINAL,
        ),
        ResolveEffectiveRunScopeTestCase(
            description="delta_and_final on snapshot model stays delta_and_final",
            requested_run_scope=AuditRunScope.DELTA_AND_FINAL,
            attached_model_materialization=MaterializationType.SNAPSHOT,
            expected_effective_run_scope=AuditRunScope.DELTA_AND_FINAL,
        ),
        ResolveEffectiveRunScopeTestCase(
            description="delta_and_final on table model degrades to final",
            requested_run_scope=AuditRunScope.DELTA_AND_FINAL,
            attached_model_materialization=MaterializationType.TABLE,
            expected_effective_run_scope=AuditRunScope.FINAL,
        ),
        ResolveEffectiveRunScopeTestCase(
            description="delta_and_final on view model degrades to final",
            requested_run_scope=AuditRunScope.DELTA_AND_FINAL,
            attached_model_materialization=MaterializationType.VIEW,
            expected_effective_run_scope=AuditRunScope.FINAL,
        ),
        ResolveEffectiveRunScopeTestCase(
            description="delta_and_final with no materialization degrades to final",
            requested_run_scope=AuditRunScope.DELTA_AND_FINAL,
            attached_model_materialization=None,
            expected_effective_run_scope=AuditRunScope.FINAL,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_run_scope_and_context_when_resolving_effective_then_returns_expected(
    test_case: ResolveEffectiveRunScopeTestCase,
) -> None:
    result: AuditRunScope = resolve_effective_run_scope(
        requested_run_scope=test_case.requested_run_scope,
        attached_model_materialization=test_case.attached_model_materialization,
    )

    assert result == test_case.expected_effective_run_scope
