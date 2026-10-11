"""Assemble the compiled project's resource facts natively."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.project_assembly._helpers.request import project_request
from sqlbuild.compiler.project_assembly._helpers.resources import project_resources
from sqlbuild.compiler.project_assembly.models import NativeProjectResources
from sqlbuild.compiler.project_assembly.types import ProjectRequestRow, ProjectResourcesRow


def assemble_native_project_resources(
    *,
    inputs: CompileInputsView,
    dialect: str | None,
    syntax_checks: tuple[tuple[tuple[str, dict[str, str] | None], ...], ...],
) -> NativeProjectResources:
    """Return the resource facts and the resource Python's assembly raises at, if any."""

    request: ProjectRequestRow
    held: list[Exception | None]
    request, held = project_request(inputs=inputs, dialect=dialect, syntax_checks=syntax_checks)
    row: ProjectResourcesRow = _native.assemble_project_resource_facts(request)
    return project_resources(inputs=inputs, row=row, held=held)
