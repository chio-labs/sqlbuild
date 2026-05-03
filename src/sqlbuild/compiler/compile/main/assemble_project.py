"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs


def assemble_project(inputs: CompileProjectInputs) -> CompiledProject:
    """Convert compile inputs into the planner-ready project view."""

    return assemble_compiled_project(inputs)
