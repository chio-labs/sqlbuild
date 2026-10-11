"""A compile's attached inputs, held by its native owner when it finished every model."""

from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compile_inputs_view_impl


def compile_inputs_view(
    *, fields: dict[str, Any], native_project: _native.NativeCompiledProject | None
) -> CompileInputsView:
    """The native owner's inputs view when it holds every model input; else a record."""

    return compile_inputs_view_impl(fields=fields, native_project=native_project)
