"""Compile validation for attached audits that gate their target."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.constants import ATTACHED_AUDIT_READS_OWN_DEPENDANT_CODE
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.graph.main._attached_audit_gate_cycles import attached_audit_gate_cycles
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge

_RESOURCE_LABELS: dict[CompiledResourceType, str] = {
    CompiledResourceType.MODEL: "model",
    CompiledResourceType.SOURCE: "source",
    CompiledResourceType.SEED: "seed",
    CompiledResourceType.UDF: "function",
    CompiledResourceType.TABLE_FN: "table function",
}


def attached_audit_gate_diagnostics(*, project: CompiledProject) -> tuple[CompilerDiagnostic, ...]:
    """Return a P005 error for each attached audit that reads a resource built from its target."""

    audit_paths: dict[str, Path] = {
        audit.name: audit.audit_file.relative_path for audit in project.audits
    }
    return tuple(
        _cycle_diagnostic(cycle=cycle, audit_path=audit_paths.get(cycle.audit_name))
        for cycle in attached_audit_gate_cycles(project=project)
    )


def _cycle_diagnostic(
    *, cycle: AttachedAuditGateEdge, audit_path: Path | None
) -> CompilerDiagnostic:
    target: str = _describe(cycle.target)
    read: str = _describe(cycle.read)
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=ATTACHED_AUDIT_READS_OWN_DEPENDANT_CODE,
        message=(
            f"Audit '{cycle.audit_name}' on {target} reads {read}, which depends on "
            f"'{cycle.target.name}'; an attached audit gates its target, so it cannot wait for a "
            "resource built from that target"
        ),
        resource_type=cycle.target.resource_type,
        resource_name=cycle.target.name,
        path=audit_path,
        help=(
            f"write a singular audit under audits/singular/ that references both "
            f"'{cycle.target.name}' and '{cycle.read.name}'; it runs once both are built"
        ),
    )


def _describe(key: CompiledObjectKey) -> str:
    return f"{_RESOURCE_LABELS[CompiledResourceType(key.resource_type)]} '{key.name}'"
