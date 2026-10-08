"""Build fast column lineage facts natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage.models import ProjectColumnLineage


def build_native_column_lineage(
    *, project: CompiledProject, dialect: str | None, model_names: frozenset[str] | None
) -> ProjectColumnLineage | None:
    """Return the fast lineage graph, or None where Python must build it."""

    return None
