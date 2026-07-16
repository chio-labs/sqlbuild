"""Public typed dependency references for SQL graph resources."""

from __future__ import annotations

from sqlbuild.python_nodes.main.build_model_ref import build_model_ref
from sqlbuild.python_nodes.main.build_source_ref import build_source_ref
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind as SqlResourceRefKind


def model(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild model."""

    return build_model_ref(name)


def source(name: str) -> SqlResourceRef:
    """Return a typed dependency reference to a SQLBuild source."""

    return build_source_ref(name)
