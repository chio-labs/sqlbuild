"""Public model materialization label entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.materialization_labels import (
    model_materialization_label as _model_materialization_label,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry


def model_materialization_label(entry: ModelPlanEntry) -> str:
    """Return the full materialization label used in plan summaries."""

    return _model_materialization_label(entry)
