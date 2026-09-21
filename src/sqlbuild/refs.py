"""Public typed dependency references for SQL graph resources."""

from sqlbuild.python_nodes.main.build_model_ref import build_model_ref as model
from sqlbuild.python_nodes.main.build_source_ref import build_source_ref as source
from sqlbuild.python_nodes.models import SqlResourceRef as SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind as SqlResourceRefKind

__all__ = ("SqlResourceRef", "SqlResourceRefKind", "model", "source")
