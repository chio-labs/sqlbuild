"""Build a project graph with explicit deep-analysis selection."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompileAnalysisSelection,
    CompiledProject,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline._helpers.graph import build_project_graph_impl
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


def build_project_graph_with_analysis_selection(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    analysis_selection: CompileAnalysisSelection,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ProjectGraph:
    """Build a static graph with an explicit deep-analysis selection."""

    if on_progress is not None:
        on_progress("Compiling project...")
    compile_start: float = time.monotonic()
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
        analysis_selection=analysis_selection,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.monotonic() - compile_start:.2f}s)")
    return build_project_graph_impl(project)
