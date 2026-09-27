"""Compile validation for attached audits that gate their target."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import ATTACHED_AUDIT_READS_OWN_DEPENDANT_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.graph.main._attached_audit_gate_cycle import attached_audit_gate_cycle
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge

_RESOURCE_LABELS: dict[CompiledResourceType, str] = {
    CompiledResourceType.MODEL: "model",
    CompiledResourceType.SOURCE: "source",
    CompiledResourceType.SEED: "seed",
    CompiledResourceType.UDF: "function",
    CompiledResourceType.TABLE_FN: "table function",
}


def validate_attached_audit_gates(*, project: CompiledProject) -> None:
    """Reject attached audits that would wait for a resource built from their own target."""

    cycle: AttachedAuditGateEdge | None = attached_audit_gate_cycle(project=project)
    if cycle is None:
        return
    target: str = _describe(cycle.target)
    read: str = _describe(cycle.read)
    raise CompileInputError(
        f"Audit '{cycle.audit_name}' on {target} reads {read}, which depends on "
        f"'{cycle.target.name}'; an attached audit gates its target, so it cannot wait for a "
        "resource built from that target",
        code=ATTACHED_AUDIT_READS_OWN_DEPENDANT_CODE,
        help=(
            f"write a singular audit under audits/singular/ that references both "
            f"'{cycle.target.name}' and '{cycle.read.name}'; it runs once both are built"
        ),
    )


def _describe(key: CompiledObjectKey) -> str:
    return f"{_RESOURCE_LABELS[CompiledResourceType(key.resource_type)]} '{key.name}'"
