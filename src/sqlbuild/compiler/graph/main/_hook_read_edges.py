"""Python hook read ordering edge entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.hook_reads import hook_read_edges_impl
from sqlbuild.compiler.graph.models import HookReadEdge


def hook_read_edges(*, project: CompiledProject) -> tuple[HookReadEdge, ...]:
    """Return edges from resources a Python hook declares it reads to the model running it."""

    return hook_read_edges_impl(project=project)
