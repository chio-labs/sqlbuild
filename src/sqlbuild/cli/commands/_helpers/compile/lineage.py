"""Compile command lineage helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.compiler.lineage.main.columns import build_project_column_lineage
from sqlbuild.compiler.lineage.models import ProjectColumnLineage
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph


def build_compile_lineage(
    *,
    graph: ProjectGraph,
    dialect: str | None,
    mode: CompileLineageMode,
) -> ProjectColumnLineage | None:
    match mode:
        case CompileLineageMode.NONE:
            return None
        case CompileLineageMode.FAST:
            return build_project_column_lineage(
                project=graph.project,
                dialect=dialect,
                mode=ColumnLineageMode.FAST,
            )
        case CompileLineageMode.RICH:
            return build_project_column_lineage(
                project=graph.project,
                dialect=dialect,
                mode=ColumnLineageMode.RICH,
            )


def compile_analysis_lineage_mode(mode: CompileLineageMode) -> ColumnLineageMode:
    if mode == CompileLineageMode.RICH:
        return ColumnLineageMode.RICH
    return ColumnLineageMode.FAST
