"""Public operation for building source-load execution indexes."""

from __future__ import annotations

from sqlbuild._native import DiscoveredLoaderFunction, SourceEntry
from sqlbuild.executor.load._helpers.execution import (
    build_load_execution_indexes as _build_load_execution_indexes,
)
from sqlbuild.executor.load.models import LoadExecutionIndexes


def build_load_execution_indexes(
    *,
    sources: tuple[SourceEntry, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> LoadExecutionIndexes:
    """Build reusable indexes for load execution and dependency handling."""

    return _build_load_execution_indexes(sources=sources, loader_functions=loader_functions)
