"""Test helpers for audit rendering tests."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.discovery.main.builtins import builtin_adapter_classes
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.spec.contracts.models import SourceEntry


def build_render_adapter(adapter_name: str | None) -> BaseAdapter | None:
    """Build an optional adapter for audit render tests."""

    return _RENDER_ADAPTER_BUILDERS[adapter_name is None](adapter_name)


def _build_named_render_adapter(adapter_name: str | None) -> BaseAdapter | None:
    return builtin_adapter_classes()[cast(str, adapter_name)]()


def _build_no_render_adapter(adapter_name: str | None) -> BaseAdapter | None:
    del adapter_name
    return None


_RENDER_ADAPTER_BUILDERS: MappingProxyType[bool, Callable[[str | None], BaseAdapter | None]] = (
    MappingProxyType({False: _build_named_render_adapter, True: _build_no_render_adapter})
)


def build_render_model_locations(
    targets: dict[str, str],
) -> dict[str, CompiledRelationLocation]:
    """Build model locations from a simple name-to-qualified mapping."""

    return {
        name: CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }


def build_render_seed_locations(
    targets: dict[str, str],
) -> dict[str, CompiledRelationLocation]:
    """Build seed locations from a simple name-to-qualified mapping."""

    return {
        name: CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }


def build_render_source_map(
    entries: dict[str, tuple[str | None, str | None, str | None]],
) -> dict[str, SourceEntry]:
    """Build source map from simple tuples of (database, schema, table)."""

    return {
        name: SourceEntry(
            name=name,
            database=parts[0],
            schema=parts[1],
            table=parts[2],
        )
        for name, parts in entries.items()
    }


def build_audit_plan_entry(
    *,
    name: str,
    unresolved_sql: str,
    resolved_sql: str,
    attached_column_name: str | None = None,
    severity: AuditSeverity = AuditSeverity.ERROR,
    effective_run_scope: AuditRunScope = AuditRunScope.FINAL,
    attachment_kind: AuditAttachmentKind = AuditAttachmentKind.MODEL,
    always_run: bool = False,
) -> AuditPlanEntry:
    """Build a minimal model-attached audit plan entry for identity tests."""

    return AuditPlanEntry(
        key=_audit_key(name),
        name=name,
        resolved_sql=resolved_sql,
        unresolved_sql=unresolved_sql,
        attachment_kind=attachment_kind,
        severity=severity,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=effective_run_scope,
        attached_target_name="orders",
        attached_column_name=attached_column_name,
        always_run=always_run,
    )


def _audit_key(name: str) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name)
