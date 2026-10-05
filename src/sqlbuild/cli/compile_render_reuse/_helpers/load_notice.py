"""Lifecycle lines for loading a large render store before the compile status starts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlbuild.cli.compile_render_reuse.constants import (
    RENDER_LOAD_DONE_MESSAGE,
    RENDER_LOAD_FAILED_MESSAGE,
    RENDER_LOAD_NOTICE_BYTES,
    RENDER_LOAD_START_MESSAGE,
)
from sqlbuild.cli.compile_reuse.constants import BYTES_PER_MEBIBYTE, REUSE_RENDER_STATE_SUFFIX


def start_load_notice(*, entry_path: Path) -> float | None:
    """Announce loading on stderr when the slot's stored render files are large."""

    stored_bytes: int = sum(
        _file_size(path=path)
        for path in entry_path.parent.glob(f"{entry_path.stem}-*{REUSE_RENDER_STATE_SUFFIX}")
    )
    if stored_bytes < RENDER_LOAD_NOTICE_BYTES:
        return None
    print(
        RENDER_LOAD_START_MESSAGE.format(mebibytes=stored_bytes / BYTES_PER_MEBIBYTE),
        file=sys.stderr,
    )
    return time.monotonic()


def _file_size(*, path: Path) -> int:
    """Size a stored render file, treating one removed by a concurrent compile as empty."""

    try:
        return path.stat().st_size
    except OSError:
        return 0


def finish_load_notice(*, started: float | None, loaded: bool) -> None:
    """Report whether an announced load produced usable renders."""

    if started is None:
        return
    message: str = RENDER_LOAD_DONE_MESSAGE if loaded else RENDER_LOAD_FAILED_MESSAGE
    print(message.format(seconds=time.monotonic() - started), file=sys.stderr)
