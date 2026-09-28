"""Public typed references for SQL graph resources."""

from sqlbuild.python_nodes.models import SqlResourceRef as SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind as SqlResourceRefKind

__all__ = ("SqlResourceRef", "SqlResourceRefKind", "model", "seed", "source")


def model(name: str) -> SqlResourceRef:
    """Return a typed reference to a SQLBuild model."""

    return SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=name)


def source(name: str) -> SqlResourceRef:
    """Return a typed reference to a SQLBuild source."""

    return SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=name)


def seed(name: str) -> SqlResourceRef:
    """Return a typed reference to a SQLBuild seed."""

    return SqlResourceRef(kind=SqlResourceRefKind.SEED, name=name)
