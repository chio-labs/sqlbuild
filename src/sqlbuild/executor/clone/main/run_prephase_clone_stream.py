"""Public clone prephase streaming entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlbuild.executor.clone.helpers.prephase_progress import (
    run_prephase_clone_stream as _run_prephase_clone_stream,
)
from sqlbuild.executor.clone.types import CloneItemCallback


def run_prephase_clone_stream[RESULT](
    *,
    stream: TextIO,
    title: str,
    caused_by_names: tuple[str, ...],
    use_color: bool,
    run_clone: Callable[[CloneItemCallback], RESULT],
) -> RESULT:
    """Run clone work with shared prephase streaming output."""

    return _run_prephase_clone_stream(
        stream=stream,
        title=title,
        caused_by_names=caused_by_names,
        use_color=use_color,
        run_clone=run_clone,
    )
