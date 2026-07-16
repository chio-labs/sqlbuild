"""Construct typed references to SQLBuild sources."""

from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def build_source_ref(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild source."""

    return SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=name)
