"""Assemble the compiled project's resource facts natively for the preview compiler engine."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.project_assembly._helpers.deferrals import record_project_assembly_deferral
from sqlbuild.compiler.project_assembly._helpers.request import project_request
from sqlbuild.compiler.project_assembly._helpers.resources import project_resources
from sqlbuild.compiler.project_assembly.models import NativeProjectResources
from sqlbuild.compiler.project_assembly.types import ProjectResourcesRow


def assemble_native_project_resources(
    *,
    inputs: CompileProjectInputs,
    dialect: str | None,
    syntax_checks: tuple[tuple[tuple[str, dict[str, str] | None], ...], ...],
) -> NativeProjectResources | None:
    """Return the resource facts, or None with a deferral record where Python must assemble."""

    row: ProjectResourcesRow | None
    deferral: str | None
    row, deferral = _native.assemble_project_resource_facts(
        project_request(inputs=inputs, dialect=dialect, syntax_checks=syntax_checks)
    )
    if row is None:
        _ = record_project_assembly_deferral(kind=deferral or "unknown")
        return None
    return project_resources(inputs=inputs, row=row)
