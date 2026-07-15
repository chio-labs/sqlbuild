"""Public model execution annotation entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.materialization_labels import (
    model_execution_annotation as _model_execution_annotation,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry


def model_execution_annotation(entry: ModelPlanEntry | None) -> str:
    """Return the parenthesized model annotation used in execution progress rows."""

    return _model_execution_annotation(entry)
