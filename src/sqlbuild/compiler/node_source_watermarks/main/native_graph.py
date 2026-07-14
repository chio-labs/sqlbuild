"""Public native node source watermark graph input entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks._helpers.native_graph import (
    build_native_node_source_watermark_inputs as _build_native_node_source_watermark_inputs,
)
from sqlbuild.compiler.node_source_watermarks.models import NativeNodeSourceWatermarkInputs
from sqlbuild.compiler.planner.models import PlanOutput


def build_native_node_source_watermark_inputs(
    *, plan: PlanOutput
) -> NativeNodeSourceWatermarkInputs:
    """Build native execution inputs for node source watermark propagation."""

    return _build_native_node_source_watermark_inputs(plan=plan)
