"""Public prephase header writer entrypoint."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.executor.clone.helpers.prephase_progress import (
    write_prephase_header as _write_prephase_header,
)


def write_prephase_header(*, stream: TextIO, title: str, use_color: bool) -> None:
    """Write a shared prephase header."""

    _write_prephase_header(stream=stream, title=title, use_color=use_color)
