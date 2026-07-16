"""Render a dbt node result."""

from typing import TextIO

from sqlbuild.integrations.dbt._helpers.runtime.event_stream import (
    render_dbt_node_result as _render,
)
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult
from sqlbuild.presentation.classes.cli_style import CliStyle


def render_dbt_node_result(
    *,
    stream: TextIO,
    style: CliStyle,
    result: DbtNodeExecutionResult,
    display_index: int | None = None,
    display_total: int | None = None,
    detail: str = "",
) -> None:
    """Render one dbt node execution result."""

    _ = _render(
        stream=stream,
        style=style,
        result=result,
        display_index=display_index,
        display_total=display_total,
        detail=detail,
    )
