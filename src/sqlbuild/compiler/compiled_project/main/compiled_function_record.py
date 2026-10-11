"""A compiled function as a `CompiledFunction` record, for callers that copy or expose it."""

from sqlbuild.compiler.compile.types import CompiledFunctionView
from sqlbuild.compiler.compiled_project._helpers.model_updates import (
    compiled_function_record_impl,
)


def compiled_function_record(function: CompiledFunctionView) -> CompiledFunctionView:
    """The function as a `CompiledFunction`, projected from its owner when it is a native view."""

    return compiled_function_record_impl(function)
