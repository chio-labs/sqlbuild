"""dbt progress reporting callback helper."""

from __future__ import annotations

from collections.abc import Callable


def report_progress(*, on_progress: Callable[[str], None] | None, message: str) -> None:
    """Invoke the optional progress callback with a message."""

    if on_progress is not None:
        on_progress(message)
