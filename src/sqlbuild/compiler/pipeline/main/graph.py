"""Build the static compiled project dependency graph."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompileAnalysisSelection,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.graph.main._build_lineage_downstream_deps import (
    build_lineage_downstream_deps,
)
from sqlbuild.compiler.graph.main._build_lineage_upstream_deps import (
    build_lineage_upstream_deps,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline._helpers.graph import build_static_all_keys
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection._build_model_path_index import (
    build_model_path_index,
)
from sqlbuild.compiler.planner.main.selection._build_model_tag_index import (
    build_model_tag_index,
)
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
        analysis_selection=CompileAnalysisSelection(no_cache=no_cache),
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.monotonic() - compile_start:.2f}s)")
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_upstream_deps(project)
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_downstream_deps(upstream_deps)
    )
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index=build_model_tag_index(project),
        path_index=build_model_path_index(project),
        all_keys=build_static_all_keys(project),
    )
