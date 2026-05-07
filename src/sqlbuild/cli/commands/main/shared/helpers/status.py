"""Shared CLI status rendering helpers."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console


@contextmanager
def maybe_status(message: str, *, enabled: bool) -> Iterator[None]:
    """Render a stderr spinner for long-running interactive operations."""

    if not enabled or not sys.stderr.isatty():
        yield
        return

    console: Console = Console(stderr=True)
    with console.status(message, spinner="dots"):
        yield
