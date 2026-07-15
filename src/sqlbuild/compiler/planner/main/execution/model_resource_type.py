"""Public model resource type display entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.materialization_labels import (
    model_resource_type as _model_resource_type,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry


def model_resource_type(entry: ModelPlanEntry | None) -> str:
    """Return the left-column resource type used in execution progress rows."""

    return _model_resource_type(entry)
