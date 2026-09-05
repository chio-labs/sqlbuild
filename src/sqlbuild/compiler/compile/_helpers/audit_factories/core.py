"""Audit-factory model attachment helpers."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.models import DiscoveredAuditFactory, DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SourceLocation


def build_audit_factory_orphan_diagnostics(
    *, discovered_inputs: DiscoveredProjectInputs
) -> tuple[CompilerDiagnostic, ...]:
    """Return warnings for audit factories that no model explicitly attaches."""

    referenced_names: set[str] = set()
    for model_file in discovered_inputs.model_files:
        raw_references: object | None = model_file.header_values.get("audit_factories")
        if isinstance(raw_references, list):
            referenced_names.update(item for item in raw_references if isinstance(item, str))
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILE,
            severity=DiagnosticSeverity.WARNING,
            code="C216",
            message=(
                f"Audit factory '{factory.name}' is not referenced by any model and will not "
                "produce audits"
            ),
            resource_type=CompiledResourceType.AUDIT,
            resource_name=factory.name,
            location=SourceLocation(path=factory.relative_path, line=factory.line, column=1),
        )
        for factory in discovered_inputs.audit_factories
        if factory.name not in referenced_names
    )


def parse_model_header_audit_factories(
    *,
    raw_audit_factories: object | None,
    file_path: Path,
    model_name: str,
    audit_factories: tuple[DiscoveredAuditFactory, ...],
) -> tuple[SchemaAuditInstance, ...]:
    """Resolve explicitly named factories into model audit instances."""

    if raw_audit_factories is None:
        return ()
    if not isinstance(raw_audit_factories, list):
        raise CompileInputError(f"{file_path} model audit_factories must be a list")
    factories_by_name: dict[str, DiscoveredAuditFactory] = {
        factory.name: factory for factory in audit_factories
    }
    references: list[str] = []
    for value in raw_audit_factories:
        if not isinstance(value, str) or not value.strip():
            raise CompileInputError(
                f"{file_path} model audit_factories entries must be bare identifiers"
            )
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise CompileInputError(
                f"{file_path} model audit_factories entry '{value}' must be a bare identifier"
            )
        if value in references:
            raise CompileInputError(
                f"model '{model_name}' in {file_path} references audit factory '{value}' more "
                "than once"
            )
        references.append(value)

    generated: list[SchemaAuditInstance] = []
    for reference in references:
        factory: DiscoveredAuditFactory | None = factories_by_name.get(reference)
        if factory is None:
            available: str = ", ".join(sorted(factories_by_name)) or "none discovered"
            raise CompileInputError(
                f"model '{model_name}' in {file_path} references unknown audit factory "
                f"'{reference}'. Available audit factories: {available}"
            )
        for case in factory.cases:
            generated.append(
                SchemaAuditInstance(
                    definition_name=case.definition,
                    name=case.name,
                    arguments=dict(case.arguments),
                    severity=case.severity,
                    run_scope=case.run_scope,
                    always_run=case.always_run,
                    description=case.description,
                    thresholds=case.thresholds,
                    minimum_samples=case.minimum_samples,
                    location=SourceLocation(
                        path=factory.relative_path,
                        line=factory.line,
                        column=1,
                    ),
                )
            )
    return tuple(generated)


def merge_validated_model_audits(
    *,
    direct_audits: tuple[SchemaAuditInstance, ...],
    generated_audits: tuple[SchemaAuditInstance, ...],
    model_name: str,
    file_path: Path,
) -> tuple[SchemaAuditInstance, ...]:
    """Append generated audits while rejecting generated identity collisions."""

    merged: tuple[SchemaAuditInstance, ...] = (*direct_audits, *generated_audits)
    seen_names: set[str] = {audit.name or audit.definition_name for audit in direct_audits}
    for audit in generated_audits:
        identity_name: str = audit.name or audit.definition_name
        if identity_name in seen_names:
            raise CompileInputError(
                f"model '{model_name}' in {file_path} has duplicate audit case name "
                f"'{identity_name}' across direct and factory attachments"
            )
        seen_names.add(identity_name)
    return merged
