"""Audits attached natively by the compile's model loop and held by its native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.main._builtins import builtin_audit_definitions
from sqlbuild.compiler.auditing.main._parse_audit_header_policies import (
    parse_audit_header_policies,
)
from sqlbuild.compiler.auditing.types import AuditEvaluationMode
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import AuditInput
from sqlbuild.compiler.discovery.models import DiscoveredAuditFile, DiscoveredProjectInputs
from sqlbuild.compiler.scopes.models import DeclarationIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind
from sqlbuild.spec.contracts.models import SettingsConfig


def attach_audits(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    effective_settings: SettingsConfig,
) -> tuple[tuple[AuditInput, ...], tuple[CompilerDiagnostic, ...]]:
    """Attach every singular audit, then each model's, source's and seed's generic audits."""

    default_severity: object | None = effective_settings.default_audit_severity
    audits, diagnostics = native_project.attach_audits(
        [_audit_file_row(audit_file) for audit_file in discovered_inputs.audit_files],
        {
            "default_severity": None if default_severity is None else str(default_severity),
            "default_run_scope": effective_settings.default_audit_run_scope,
            "builtins": [_audit_file_row(audit_file) for audit_file in builtin_audit_definitions()],
            "declaration_identity": DeclarationIdentity,
            "singular_kind": DeclarationKind.SINGULAR_AUDIT,
            "audit_kind": DeclarationKind.AUDIT,
            "resource_kinds": {kind.value: kind for kind in ResourceKind},
            "parse_policies": parse_audit_header_policies,
        },
    )
    return tuple(audits), tuple(diagnostics)


def _audit_file_row(audit_file: DiscoveredAuditFile) -> tuple[object, ...]:
    return (
        str(audit_file.file_path),
        str(audit_file.relative_path),
        audit_file.file_path.stem,
        audit_file,
        audit_file.declaration_kind is DeclarationKind.AUDIT,
        audit_file.contents,
        [
            (
                block,
                block.name,
                block.sql_body,
                block.evidence_sql,
                block.evaluation_mode == AuditEvaluationMode.MEASUREMENT,
                block.header_values,
            )
            for block in audit_file.blocks
        ],
    )
