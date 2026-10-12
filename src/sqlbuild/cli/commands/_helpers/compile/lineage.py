"""Compile command lineage helpers."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild._native import ProjectColumnLineage
from sqlbuild.cli.commands.types import CompileLineageMode
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
            return _native.build_project_column_lineage(
                graph.project, dialect, ColumnLineageMode.FAST, None
            )
        case CompileLineageMode.RICH:
            return _native.build_project_column_lineage(
                graph.project, dialect, ColumnLineageMode.RICH, None
            )


def compile_analysis_lineage_mode(mode: CompileLineageMode) -> ColumnLineageMode:
    if mode == CompileLineageMode.RICH:
        return ColumnLineageMode.RICH
    return ColumnLineageMode.FAST
