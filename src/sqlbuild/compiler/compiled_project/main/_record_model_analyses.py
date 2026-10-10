"""Transfer assembled models' typed analysis results to the native compiled project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compiled_project._helpers.rows import record_model_analyses_impl


def record_model_analyses(
    *, project: _native.NativeCompiledProject, models: tuple[CompiledModel, ...]
) -> int:
    """Attach each model's inferred columns and dynamic pivot proof to its retained facts."""

    return record_model_analyses_impl(project=project, models=models)
