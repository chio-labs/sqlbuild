"""Compile inputs with some fields changed, natively when their owner holds them."""

from typing import Any

from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.compiled_project._helpers.model_updates import inputs_with_impl


def inputs_with(*, inputs: CompileInputsView, **changes: Any) -> CompileInputsView:
    """The compile inputs with `changes`; a native view shares its owner's model inputs."""

    return inputs_with_impl(inputs=inputs, **changes)
