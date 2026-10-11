"""A compiled project as a `CompiledProject` record, for callers that copy or ship it."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compiled_project_record_impl


def compiled_project_record(
    project: CompiledProjectView, *, include_sql_expansions: bool = True
) -> CompiledProject:
    """The project as a `CompiledProject`, projected from its owner when it is a native view."""

    return compiled_project_record_impl(
        project=project, include_sql_expansions=include_sql_expansions
    )
