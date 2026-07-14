"""Public operation for building source-load execution indexes."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.helpers.execution import (
    build_load_execution_indexes as _build_load_execution_indexes,
)
from sqlbuild.executor.load.models import LoadExecutionIndexes
from sqlbuild.spec.contracts.models import SourceEntry


def build_load_execution_indexes(
    *,
    sources: tuple[SourceEntry, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> LoadExecutionIndexes:
    """Build reusable indexes for load execution and dependency handling."""

    return _build_load_execution_indexes(sources=sources, loader_functions=loader_functions)
