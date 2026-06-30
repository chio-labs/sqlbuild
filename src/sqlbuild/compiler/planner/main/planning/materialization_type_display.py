"""Public materialization type display entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner.helpers.output.materialization_labels import (
    materialization_type_display as _materialization_type_display,
)
from sqlbuild.shared.types import ExecutionResourceKind


def materialization_type_display(resource_kind: ExecutionResourceKind) -> str:
    """Return the left-column resource type for active progress rows."""

    return _materialization_type_display(resource_kind)
