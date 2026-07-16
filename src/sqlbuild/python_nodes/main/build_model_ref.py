"""Construct typed references to SQLBuild models."""

from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def build_model_ref(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild model."""

    return SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=name)
