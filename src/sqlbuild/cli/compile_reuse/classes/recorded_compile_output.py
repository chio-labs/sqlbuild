"""Compile command output that is printed and retained for later reuse."""

from __future__ import annotations

import sys


class RecordedCompileOutput:
    """Print compile notes at once and the report after storing, keeping the exact text."""

    def __init__(self) -> None:
        self._stderr_lines: list[str] = []
        self._stdout: str | None = None

    def print_stderr_line(self, line: str) -> None:
        """Print one stderr result line, such as a note, and record it."""

        print(line, file=sys.stderr)
        self._stderr_lines.append(line)

    def record_stdout(self, text: str) -> None:
        """Record the compile report; it is printed once the compile has been stored."""

        self._stdout = f"{text}\n"

    def print_stdout(self) -> None:
        """Print the recorded compile report, if any, exactly as it is stored."""

        if self._stdout is not None:
            _ = sys.stdout.write(self._stdout)
            sys.stdout.flush()

    @property
    def stderr_lines(self) -> tuple[str, ...]:
        """Return the recorded stderr result lines in emission order."""

        return tuple(self._stderr_lines)

    @property
    def stdout(self) -> str | None:
        """Return the recorded stdout text, or None when no report was printed."""

        return self._stdout
