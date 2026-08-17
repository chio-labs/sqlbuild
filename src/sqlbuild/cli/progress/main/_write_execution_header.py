"""Generic CLI execution header output."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.progress.main._execution_header import format_execution_header
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.surface_header import format_surface_header


def write_execution_header(
    *, stream: TextIO, command: str, target: str | None, concurrency: int, use_color: bool
) -> None:
    """Write an execution header for command progress output."""

    style: CliStyle = CliStyle(use_color=use_color)
    header: str = format_execution_header(
        command=command,
        target=target,
        concurrency=concurrency,
    )
    stream.write(f"{format_surface_header(style=style, title='Execution', context=header)}\n\n")
    stream.flush()
