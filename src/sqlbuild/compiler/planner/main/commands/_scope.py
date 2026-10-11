"""Focused-command scope entrypoint."""

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner._helpers.command_planning.static import (
    resolve_static_command_scope_impl,
)
from sqlbuild.compiler.planner.models import PlannerScope, PlannerSelection


def resolve_static_command_scope(
    *, project: CompiledProjectView, selection: PlannerSelection, auto_load_sources: bool = False
) -> PlannerScope:
    """Resolve command selection through the canonical build selector phase."""

    return resolve_static_command_scope_impl(
        project=project, selection=selection, auto_load_sources=auto_load_sources
    )
