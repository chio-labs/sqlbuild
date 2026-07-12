"""Public typed dependency references for SQL graph resources."""

from __future__ import annotations

from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def model(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild model."""

    return SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=name)


def source(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild source."""

    return SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=name)
