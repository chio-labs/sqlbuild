"""The native compiled project a consumer reads for one `CompiledProject`."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compiled_project._helpers.rows import hand_built_project_impl


def compiled_project_facts(project: CompiledProject) -> _native.NativeCompiledProject:
    """The compile's retained project, or one recorded from a hand-built project."""

    if project.native_project is not None:
        return project.native_project
    return hand_built_project_impl(project)
