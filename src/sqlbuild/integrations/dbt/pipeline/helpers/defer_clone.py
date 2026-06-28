"""dbt defer-clone prephase helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.graph.core import (
    build_dbt_combined_graph,
    combined_graph_node_is_clonable,
    combined_graph_node_is_view,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.manifest.fingerprinting import (
    try_write_dbt_node_fingerprint,
)
from sqlbuild.integrations.dbt.helpers.planning.graph_projection import (
    dbt_graph_node_key,
)
from sqlbuild.integrations.dbt.helpers.planning.model_identity import (
    build_dbt_write_identity_hashes,
)
from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    build_expected_dbt_model_version_hashes,
)
from sqlbuild.integrations.dbt.helpers.reuse.production_ref import compile_production_ref_manifest
from sqlbuild.integrations.dbt.helpers.selection.selector_terms import dbt_fqn_selector_term
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtLsNode,
    DbtNodeExecutionResult,
    DbtProductionRefCompileResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.clone import execute_dbt_clone
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtSupportedResourceType
from sqlbuild.shared.helpers.graph_algorithms import (
    resolve_clone_boundary,
    resolve_skipped_view_chain,
)
from sqlbuild.spec.models.project import DbtProductionRefConfig


def run_dbt_defer_clone_prephase(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    dbt_options: DbtCliOptions,
    runner: DbtRunner,
    adapter: BaseAdapter,
    project: CompiledProject,
    connection_config: dict[str, object],
    current_manifest: DbtManifestIndex,
    unique_ids: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
) -> None:
    if not unique_ids:
        return
    production_ref: DbtProductionRefConfig = discovered_inputs.project_config.dbt.production_ref
    if production_ref.git_ref is None or production_ref.generate_schema_name_override is None:
        raise DbtInteropConfigError(
            "dbt --defer-clone-from requires [dbt.production_ref] to be configured",
            code="C350",
            help=(
                "Run sqb dbt init or set [dbt.production_ref].git_ref and "
                "generate_schema_name_override in sqlbuild_project.toml."
            ),
        )
    _report_progress(
        on_progress, f"Compiling dbt production ref git ref '{production_ref.git_ref}'..."
    )
    production_ref_start: float = time.monotonic()
    production_ref_compile: DbtProductionRefCompileResult = compile_production_ref_manifest(
        sqlbuild_project_dir=project_dir,
        dbt_options=dbt_options,
        production_ref=production_ref,
        runner=runner,
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(production_ref_compile.manifest_contents)
    )
    _report_progress(
        on_progress,
        f"Compiled dbt production ref git ref '{production_ref.git_ref}'. "
        f"({time.monotonic() - production_ref_start:.2f}s)",
    )
    selected_nodes: tuple[DbtLsNode, ...] = tuple(
        DbtLsNode(unique_id=unique_id, resource_type=DbtSupportedResourceType.MODEL)
        for unique_id in unique_ids
    )
    _report_progress(on_progress, "Cloning deferred dbt boundary relations...")
    clone_start: float = time.monotonic()
    connection: Any = adapter.connect(connection_config)
    try:
        result: CloneExecutionResult = execute_dbt_clone(
            adapter=adapter,
            connection=connection,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            selected_nodes=selected_nodes,
            hard_copy=False,
        )
        _write_defer_clone_dbt_fingerprints(
            result=result,
            adapter=adapter,
            connection=connection,
            project=project,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            unique_ids=unique_ids,
            on_progress=on_progress,
        )
    finally:
        adapter.close(connection)
    if any(item.status == CloneStatus.FAILED for item in result.item_results):
        raise DbtInteropRuntimeError("failed to clone one or more deferred dbt boundary relations")
    _report_progress(
        on_progress,
        f"Cloned deferred dbt boundary relations. ({time.monotonic() - clone_start:.2f}s)",
    )


def resolve_defer_clone_unique_ids(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    selected_sqlbuild_model_names: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
) -> frozenset[str]:
    """Resolve the first non-view dbt ancestors to clone for SQLBuild-selected boundaries."""

    selected: frozenset[DbtCombinedGraphKey] = frozenset(
        sqlbuild_model_graph_key(model_name) for model_name in selected_sqlbuild_model_names
    )

    def is_clonable(key: DbtCombinedGraphKey) -> bool:
        return key.owner == DbtCombinedGraphOwner.DBT and combined_graph_node_is_clonable(
            key=key, manifest=manifest
        )

    def is_view(key: DbtCombinedGraphKey) -> bool:
        return combined_graph_node_is_view(key=key, manifest=manifest, project=project)

    boundary: frozenset[DbtCombinedGraphKey] = resolve_clone_boundary(
        selected=selected,
        upstream=graph.upstream_deps,
        is_clonable=is_clonable,
        is_view=is_view,
    )
    unique_ids: set[str] = set(required_dbt_unique_ids)
    boundary_key: DbtCombinedGraphKey
    for boundary_key in boundary:
        unique_ids.add(boundary_key.name)
    return frozenset(unique_ids)


def resolve_defer_clone_view_chain_terms(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    selected_sqlbuild_model_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return dbt model selector terms for view ancestors that must rebuild over clones."""

    view_chain: frozenset[DbtCombinedGraphKey] = _resolve_defer_clone_view_chain_keys(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
    )
    terms: set[str] = set()
    view_key: DbtCombinedGraphKey
    for view_key in view_chain:
        if view_key.owner != DbtCombinedGraphOwner.DBT:
            continue
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(view_key.name)
        if model is not None:
            terms.add(dbt_fqn_selector_term(fqn=model.fqn, fallback=model.name))
    return tuple(sorted(terms))


def resolve_defer_clone_view_chain_unique_ids(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    selected_sqlbuild_model_names: tuple[str, ...],
) -> frozenset[str]:
    """Return dbt model unique IDs for view ancestors that must rebuild over clones."""

    view_chain: frozenset[DbtCombinedGraphKey] = _resolve_defer_clone_view_chain_keys(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
    )
    return frozenset(
        view_key.name for view_key in view_chain if view_key.owner == DbtCombinedGraphOwner.DBT
    )


def _resolve_defer_clone_view_chain_keys(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    selected_sqlbuild_model_names: tuple[str, ...],
) -> frozenset[DbtCombinedGraphKey]:
    selected: frozenset[DbtCombinedGraphKey] = frozenset(
        sqlbuild_model_graph_key(model_name) for model_name in selected_sqlbuild_model_names
    )

    def is_clonable(key: DbtCombinedGraphKey) -> bool:
        return key.owner == DbtCombinedGraphOwner.DBT and combined_graph_node_is_clonable(
            key=key, manifest=manifest
        )

    def is_view(key: DbtCombinedGraphKey) -> bool:
        return combined_graph_node_is_view(key=key, manifest=manifest, project=project)

    return resolve_skipped_view_chain(
        selected=selected,
        upstream=graph.upstream_deps,
        is_clonable=is_clonable,
        is_view=is_view,
    )


def _write_defer_clone_dbt_fingerprints(
    *,
    result: CloneExecutionResult,
    adapter: BaseAdapter,
    connection: Any,
    project: CompiledProject,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    unique_ids: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
) -> None:
    if not project.settings.query_change_tracking:
        return
    successful_names: frozenset[str] = frozenset(
        item.name
        for item in result.item_results
        if item.status == CloneStatus.SUCCESS
        and item.action in {CloneAction.CLONED, CloneAction.COPIED}
    )
    if not successful_names:
        return
    reuse_graph: DbtCombinedGraph = build_dbt_combined_graph(
        manifest=reuse_manifest, project=project
    )
    reuse_expected_version_hashes: dict[str, str | None] = build_expected_dbt_model_version_hashes(
        manifest=reuse_manifest, graph=reuse_graph
    )
    reuse_write_version_hashes: dict[GraphNodeKey, str] = build_dbt_write_identity_hashes(
        manifest=reuse_manifest,
        graph=reuse_graph,
        run_unique_ids=frozenset(unique_ids),
        expected_version_hash_by_unique_id=reuse_expected_version_hashes,
    )
    warnings: list[str] = []
    unique_id: str
    for unique_id in unique_ids:
        current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(unique_id)
        reuse_model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(unique_id)
        if (
            current_model is None
            or reuse_model is None
            or current_model.name not in successful_names
        ):
            continue
        try_write_dbt_node_fingerprint(
            result=DbtNodeExecutionResult(
                unique_id=unique_id,
                resource_type=DbtSupportedResourceType.MODEL,
                node_name=current_model.name,
                status="success",
                index=None,
                total=None,
                execution_time=None,
                materialized=None,
                relation_name=current_model.relation_name,
                database=current_model.database,
                schema=current_model.schema,
                node_checksum=reuse_model.node_checksum,
            ),
            adapter=adapter,
            connection=connection,
            run_id=project.run_id,
            fingerprint_database=project.effective_target_database,
            fingerprint_schema=project.effective_target_schema,
            target_name=project.effective_target_name,
            warnings=warnings,
            query_sql=reuse_model.query_sql,
            version_hash_override=(
                reuse_write_version_hashes.get(dbt_graph_node_key(unique_id))
                or reuse_model.node_checksum
            ),
        )
    if warnings:
        _report_progress(on_progress, "; ".join(warnings))


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
