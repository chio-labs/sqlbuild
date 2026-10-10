"""Retain the compile-input stage's models in the native compiled project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompileModelInput
from sqlbuild.compiler.compiled_project._helpers.rows import record_model_inputs_impl


def record_model_inputs(
    *, project: _native.NativeCompiledProject, model_inputs: tuple[CompileModelInput, ...]
) -> int:
    """Retain each produced model's identity, config, references, schema and declarations."""

    return record_model_inputs_impl(project=project, model_inputs=model_inputs)
