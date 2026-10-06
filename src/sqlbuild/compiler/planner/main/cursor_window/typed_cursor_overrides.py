"""Public typing of untyped `--start-cursor`/`--end-cursor` values."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    type_cursor_overrides,
)
from sqlbuild.compiler.planner.models import CursorOverrides


def typed_cursor_overrides(
    *,
    cursor_overrides: CursorOverrides | None,
    selected_models: Iterable[CompiledModel] = (),
) -> CursorOverrides | None:
    """Read `--start-cursor`/`--end-cursor` as the one cursor type of the selected models."""

    return type_cursor_overrides(cursor_overrides=cursor_overrides, selected_models=selected_models)
