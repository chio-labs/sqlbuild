"""Public operation for building a skipped source-load result."""

from __future__ import annotations

from sqlbuild._native import SourceEntry
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.load._helpers.execution import skipped_load_result as _skipped_load_result
from sqlbuild.executor.load.models import LoadExecutionResult


def skipped_load_result(
    *,
    source: SourceEntry,
    reason: str | None = None,
    mode: SkipMode = SkipMode.HARD,
) -> LoadExecutionResult:
    """Build a skipped result for a loader or source node."""

    return _skipped_load_result(source=source, reason=reason, mode=mode)
