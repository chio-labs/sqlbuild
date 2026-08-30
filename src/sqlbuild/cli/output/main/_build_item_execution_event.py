"""Public direct build item event formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_build_item_execution_event as _format_build_item_execution_event,
)
from sqlbuild.compiler.planner.models import PlanOutput


def format_build_item_execution_event(
    *, result: object, plan: PlanOutput | None, command: str = "build"
) -> str | None:
    """Format one completed build item as a JSON Lines event when it is an asset result."""

    return _format_build_item_execution_event(result=result, plan=plan, command=command)
