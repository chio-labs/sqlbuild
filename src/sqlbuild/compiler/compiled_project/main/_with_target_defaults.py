"""Fill an adapter's default schema and database into a native compiled model's destination."""

from collections.abc import Callable

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.compiled_project._helpers.model_updates import with_target_defaults_impl


def with_target_defaults(
    *,
    model: _native.NativeCompiledModel,
    defaults: tuple[str | None, str | None],
    render_qualified_name: Callable[..., str | None],
) -> CompiledModelView:
    """The model with the adapter's `(schema, database)` defaults filled into its destination."""

    return with_target_defaults_impl(
        model=model, defaults=defaults, render_qualified_name=render_qualified_name
    )
