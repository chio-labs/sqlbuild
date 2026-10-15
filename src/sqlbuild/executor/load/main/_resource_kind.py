"""Public operation for resolving a source-load resource kind."""

from __future__ import annotations

from sqlbuild._native import SourceEntry
from sqlbuild.executor.load._helpers.execution import load_resource_kind as _load_resource_kind
from sqlbuild.runtime.contracts.types import ExecutionResourceKind


def load_resource_kind(source: SourceEntry) -> ExecutionResourceKind:
    """Return the display and execution kind for one load node."""

    return _load_resource_kind(source)
