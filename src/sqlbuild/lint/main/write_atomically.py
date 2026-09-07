"""Public atomic source-file writer."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint._helpers.fixes import write_atomically as _write_atomically


def write_atomically(*, path: Path, contents: str) -> None:
    """Replace a text file atomically."""

    _write_atomically(path=path, contents=contents)
