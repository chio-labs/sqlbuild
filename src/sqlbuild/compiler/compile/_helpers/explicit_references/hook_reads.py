"""Compile validation for resources Python hooks declare they read."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import HOOK_READS_OWN_DEPENDANT_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.main._hook_read_cycle import hook_read_cycle
from sqlbuild.compiler.graph.models import HookReadEdge
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def validate_hook_reads(*, project: CompiledProject) -> None:
    """Reject unknown declared hook reads and reads that would wait for the hook's own model."""

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
    cycle: HookReadEdge | None = hook_read_cycle(project=project)
    if cycle is None:
        return
    raise CompileInputError(
        f"Python hook '{cycle.hook_name}' on {_describe(cycle.gated)} reads "
        f"{_describe(cycle.read)}, "
        f"which depends on '{cycle.gated.name}'; a hook runs as part of its model, so it cannot "
        "wait for a resource built from that model",
        code=HOOK_READS_OWN_DEPENDANT_CODE,
        help=(
            f"attach the hook to a model built after '{cycle.read.name}', or drop the read and "
            f"use ctx.destination for '{cycle.gated.name}' itself"
        ),
    )


def _describe(key: CompiledObjectKey) -> str:
    return f"{key.resource_type} '{key.name}'"
