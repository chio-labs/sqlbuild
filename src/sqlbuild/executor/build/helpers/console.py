"""Live terminal console for build execution progress."""

from __future__ import annotations

import sys
import time
from typing import IO

from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.helpers.output.colors import supports_color


class BuildConsole:
    """Handles live progress output during build execution."""

    def __init__(
        self,
        *,
        stream: IO[str] | None = None,
        use_color: bool | None = None,
        total: int = 0,
    ) -> None:
        self._stream: IO[str] = stream or sys.stdout
        self._is_tty: bool = hasattr(self._stream, "isatty") and self._stream.isatty()
        self._use_color: bool = use_color if use_color is not None else supports_color()
        self._style: CliStyle = CliStyle(use_color=self._use_color)
        self._total: int = total
        self._counter: int = 0
        self._current_name: str | None = None
        self._current_type: str | None = None
        self._start_time: float | None = None

    @property
    def use_color(self) -> bool:
        return self._use_color

    @property
    def counter(self) -> int:
        return self._counter

    def increment_counter(self) -> int:
        self._counter += 1
        return self._counter

    def on_node_start(self, *, name: str, resource_type: str) -> None:
        """Show a transient 'running' line for the current node."""

        self._current_name = name
        self._current_type = resource_type
        self._start_time = time.monotonic()
        if self._is_tty:
            counter_str: str = self._format_counter(self._counter + 1)
            status: str = self._style.status("...")
            line: str = f"  {counter_str}  {resource_type:<6} {name:<40} {status}"
            self._stream.write(f"\r{line}")
            self._stream.flush()

    def on_node_complete(self, *, line: str) -> None:
        """Replace the transient line with the final result."""

        if self._is_tty and self._current_name is not None:
            self._stream.write("\r\033[K")
        self._stream.write(line + "\n")
        self._stream.flush()
        self._current_name = None
        self._current_type = None
        self._start_time = None

    def on_sub_line(self, *, line: str) -> None:
        """Print an indented sub-line (audit/test result)."""

        self._stream.write(line + "\n")
        self._stream.flush()

    def print_header(self, header: str) -> None:
        """Print the build header line."""

        self._stream.write(header + "\n\n")
        self._stream.flush()

    def print_footer(self, footer: str) -> None:
        """Print the build footer (summary)."""

        self._stream.write("\n" + footer + "\n")
        self._stream.flush()

    def _format_counter(self, counter: int) -> str:
        return f"{counter}/{self._total}".rjust(len(str(self._total)) * 2 + 1)
