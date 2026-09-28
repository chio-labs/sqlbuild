"""Compile validation for resources model hooks read."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import HOOK_READS_OWN_DEPENDANT_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
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
from sqlbuild.compiler.graph.main._hook_read_cycles import hook_read_cycles
from sqlbuild.compiler.graph.models import HookReadEdge
from sqlbuild.compiler.graph.types import HookReadType
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def hook_read_diagnostics(*, project: CompiledProject) -> tuple[CompilerDiagnostic, ...]:
    """Reject unknown hook reads; return a P007 error for each read of a hook's own dependant."""

    known: dict[SqlResourceRefKind, frozenset[str]] = {
        SqlResourceRefKind.MODEL: frozenset(model.name for model in project.models),
        SqlResourceRefKind.SOURCE: frozenset(source.name for source in project.sources),
        SqlResourceRefKind.SEED: frozenset(seed.name for seed in project.seeds),
    }
    for hook in sorted(project.hook_functions, key=lambda item: item.name):
        ref: SqlResourceRef
        for ref in hook.reads:
            if ref.name not in known[ref.kind]:
                raise CompileInputError(
                    f"Python hook '{hook.name}' in '{hook.relative_path.as_posix()}' reads unknown "
                    f"{ref.kind.value} '{ref.name}'"
                )
    return tuple(_cycle_diagnostic(cycle) for cycle in hook_read_cycles(project=project))


def _cycle_diagnostic(cycle: HookReadEdge) -> CompilerDiagnostic:
    destination: str = (
        "ctx.destination"
        if cycle.hook_type is HookReadType.PYTHON
        else "@@CTX:destination.qualified"
    )
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=HOOK_READS_OWN_DEPENDANT_CODE,
        message=(
            f"{cycle.label} on {_describe(cycle.gated)} reads "
            f"{_describe(cycle.read)}, which depends on '{cycle.gated.name}'; a hook runs as "
            "part of its model, so it cannot wait for a resource built from that model"
        ),
        resource_type=CompiledResourceType.MODEL,
        resource_name=cycle.gated.name,
        path=cycle.hook_path,
        help=(
            f"attach the hook to a model built after '{cycle.read.name}', or drop the read and "
            f"use {destination} for '{cycle.gated.name}' itself"
        ),
    )


def _describe(key: CompiledObjectKey) -> str:
    return f"{key.resource_type} '{key.name}'"
