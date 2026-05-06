"""Column lineage analyzer entry point."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.lineage.helpers.columns import (
    build_project_column_lineage as _build_project_column_lineage,
)
from sqlbuild.compiler.lineage.helpers.fast_columns import (
    build_fast_project_column_lineage,
)
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.lineage.types import ColumnLineageMode


def build_project_column_lineage(
    project: CompiledProject,
    *,
    dialect: str | None = None,
    mode: ColumnLineageMode = ColumnLineageMode.RICH,
) -> ProjectColumnLineage | None:
    """Build a sidecar project column lineage graph for compiled models."""

    match mode:
        case ColumnLineageMode.FAST:
            return build_fast_project_column_lineage(project, dialect=dialect)
        case ColumnLineageMode.RICH:
            return _build_project_column_lineage(project, dialect=dialect)
