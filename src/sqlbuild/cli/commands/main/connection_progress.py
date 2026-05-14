"""Connection progress public entry for cross-domain orchestration."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter


def build_connection_progress_reporter(
    *,
    adapter_name: str,
    stream: TextIO,
    blank_line_after_complete: bool = False,
    use_color: bool = False,
) -> ConnectionProgressReporter:
    """Build a connection progress reporter."""

    return ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=stream,
        blank_line_after_complete=blank_line_after_complete,
        use_color=use_color,
    )
