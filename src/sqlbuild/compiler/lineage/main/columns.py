"""Column lineage analyzer entry point."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage.helpers.columns import (
    build_project_column_lineage as _build_project_column_lineage,
)
from sqlbuild.compiler.lineage.models import ProjectColumnLineage


def build_project_column_lineage(
    project: CompiledProject,
    *,
    dialect: str | None = None,
) -> ProjectColumnLineage | None:
    """Build a sidecar project column lineage graph for compiled models."""

    return _build_project_column_lineage(project, dialect=dialect)
