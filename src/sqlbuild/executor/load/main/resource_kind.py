"""Public operation for resolving a source-load resource kind."""

from __future__ import annotations

from sqlbuild.executor.load.helpers.execution import load_resource_kind as _load_resource_kind
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.contracts.models import SourceEntry


def load_resource_kind(source: SourceEntry) -> ExecutionResourceKind:
    """Return the display and execution kind for one load node."""

    return _load_resource_kind(source)
