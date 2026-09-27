"""Python hook read cycle detection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.hook_reads import hook_read_cycle_impl
from sqlbuild.compiler.graph.models import HookReadEdge


def hook_read_cycle(*, project: CompiledProject) -> HookReadEdge | None:
    """Return the first declared hook read that depends on the model running the hook."""

    return hook_read_cycle_impl(project=project)
