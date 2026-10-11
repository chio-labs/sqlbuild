"""A compiled model as a `CompiledModel` record, for callers that copy or ship it."""

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compiled_model_record_impl


def compiled_model_record(model: CompiledModelView) -> CompiledModel:
    """The model as a `CompiledModel`, projected from its owner when it is a native view."""

    return compiled_model_record_impl(model)
