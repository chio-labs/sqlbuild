"""Execute a dbt JSON event stream."""

from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.integrations.dbt.helpers.runtime.event_stream import (
    execute_dbt_json_event_stream as _execute,
)
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult


def execute_dbt_json_event_stream(
    *,
    argv: tuple[str, ...],
    cwd: Path | None,
    stream: TextIO,
    use_color: bool,
    target_path: Path | None,
    display_total: int | None = None,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None = None,
    detail_by_unique_id: dict[str, str] | None = None,
    enable_status: bool = True,
) -> tuple[int, tuple[DbtNodeExecutionResult, ...]]:
    """Run dbt and render SQLBuild-styled JSON events."""

    return _execute(
        argv=argv,
        cwd=cwd,
        stream=stream,
        use_color=use_color,
        target_path=target_path,
        display_total=display_total,
        on_node_result=on_node_result,
        detail_by_unique_id=detail_by_unique_id,
        enable_status=enable_status,
    )
