"""Audit-factory model attachment helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import SourceLocation


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
