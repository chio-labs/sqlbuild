"""A compiled source as a `CompiledSource` record, for callers that copy or expose it."""

from sqlbuild.compiler.compile.models import CompiledSource
from sqlbuild.compiler.compile.types import CompiledSourceView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compiled_source_record_impl


def compiled_source_record(source: CompiledSourceView) -> CompiledSource:
    """The source as a `CompiledSource`, projected from its owner when it is a native view."""

    return compiled_source_record_impl(source)
