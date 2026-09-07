"""Build the static compiled project dependency graph."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompileAnalysisSelection
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.main.selected_graph import (
    build_project_graph_with_analysis_selection,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


def build_project_graph(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    no_cache: bool = False,
) -> ProjectGraph:
    """Build the static dependency graph for a compiled project."""

    return build_project_graph_with_analysis_selection(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
        on_progress=on_progress,
        analysis_selection=CompileAnalysisSelection(no_cache=no_cache),
    )
