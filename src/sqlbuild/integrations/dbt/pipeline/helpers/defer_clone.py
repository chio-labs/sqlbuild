"""dbt defer-clone prephase helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.node_source_watermarks.constants import NODE_SOURCE_WATERMARK_TABLE_NAME
from sqlbuild.compiler.node_source_watermarks.main.read import read_latest_node_source_watermarks
from sqlbuild.compiler.node_source_watermarks.main.write import write_node_source_watermark_records
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
)
from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.executor.clone.main.run_prephase_clone_stream import run_prephase_clone_stream
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.graph.core import (
    build_dbt_combined_graph,
    combined_graph_node_is_clonable,
    combined_graph_node_is_view,
    dbt_model_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.manifest.fingerprinting import (
    build_dbt_fingerprint_destination,
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
    DbtDeferClonePrephaseContext,
    DbtLsNode,
    DbtNodeExecutionResult,
    DbtProductionRefCompileResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.clone import execute_dbt_clone
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtSupportedResourceType
from sqlbuild.shared.helpers.graph.algorithms import (
    resolve_clone_boundary,
    resolve_skipped_view_chain,
)
from sqlbuild.shared.models import RelationLookup
from sqlbuild.spec.models.project import DbtProductionRefConfig


def resolve_dbt_defer_clone_from(
    *,
    cli_defer_clone_from: bool | None,
    project_defer_clone_from: bool,
    local_defer_clone_from: bool | None,
) -> bool:
    """Resolve dbt defer-clone enablement from CLI, local config, and project config."""

    if cli_defer_clone_from is not None:
        return cli_defer_clone_from
    if local_defer_clone_from is not None:
        return local_defer_clone_from
    return project_defer_clone_from


def run_dbt_defer_clone_prephase(
    *,
    context: DbtDeferClonePrephaseContext,
    current_manifest: DbtManifestIndex,
    unique_ids: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
    output_stream: TextIO,
    use_color: bool,
    caused_by_names: tuple[str, ...],
) -> CloneExecutionResult | None:
    project_dir: Path = context.project_dir
    discovered_inputs: DiscoveredProjectInputs = context.discovered_inputs
    dbt_options: DbtCliOptions = context.dbt_options
    runner: DbtRunner = context.runner
    adapter: BaseAdapter = context.adapter
    project: CompiledProject = context.project
    connection_config: dict[str, object] = context.connection_config
    if not unique_ids:
        report_progress(
            on_progress, message="defer-clone enabled but no clonable dbt boundary resolved."
        )
        return None
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
    report_progress(
        on_progress, message=f"Compiling dbt production ref git ref '{production_ref.git_ref}'..."
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
    report_progress(
        on_progress,
        message=f"Compiled dbt production ref git ref '{production_ref.git_ref}'. "
        f"({time.monotonic() - production_ref_start:.2f}s)",
    )
    selected_nodes: tuple[DbtLsNode, ...] = tuple(
        DbtLsNode(unique_id=unique_id, resource_type=DbtSupportedResourceType.MODEL)
        for unique_id in unique_ids
    )

    def run_clone(on_item: Any) -> CloneExecutionResult:
        connection: Any = adapter.connect(connection_config)
        try:
            result: CloneExecutionResult = execute_dbt_clone(
                adapter=adapter,
                connection=connection,
                current_manifest=current_manifest,
                reuse_manifest=reuse_manifest,
                selected_nodes=selected_nodes,
                hard_copy=False,
                on_item=on_item,
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
            _write_defer_clone_dbt_node_source_watermarks(
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
        return result

    result: CloneExecutionResult = run_prephase_clone_stream(
        stream=output_stream,
        title="dbt defer clone",
        caused_by_names=caused_by_names,
        use_color=use_color,
        run_clone=run_clone,
    )
    if any(item.status == CloneStatus.FAILED for item in result.item_results):
        raise DbtInteropRuntimeError("failed to clone one or more deferred dbt boundary relations")
    return result


def resolve_defer_clone_unique_ids(
    *,
    graph: DbtCombinedGraph,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    selected_sqlbuild_model_names: tuple[str, ...],
    selected_dbt_unique_ids: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
) -> frozenset[str]:
    """Resolve the first non-view dbt ancestors to clone for selected boundaries."""

    selected: frozenset[DbtCombinedGraphKey] = _defer_clone_seed_keys(
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
        selected_dbt_unique_ids=selected_dbt_unique_ids,
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
    selected_dbt_unique_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return dbt model selector terms for view ancestors that must rebuild over clones."""

    view_chain: frozenset[DbtCombinedGraphKey] = _resolve_defer_clone_view_chain_keys(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
        selected_dbt_unique_ids=selected_dbt_unique_ids,
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
    selected_dbt_unique_ids: tuple[str, ...],
) -> frozenset[str]:
    """Return dbt model unique IDs for view ancestors that must rebuild over clones."""

    view_chain: frozenset[DbtCombinedGraphKey] = _resolve_defer_clone_view_chain_keys(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
        selected_dbt_unique_ids=selected_dbt_unique_ids,
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
    selected_dbt_unique_ids: tuple[str, ...],
) -> frozenset[DbtCombinedGraphKey]:
    selected: frozenset[DbtCombinedGraphKey] = _defer_clone_seed_keys(
        selected_sqlbuild_model_names=selected_sqlbuild_model_names,
        selected_dbt_unique_ids=selected_dbt_unique_ids,
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


def _defer_clone_seed_keys(
    *,
    selected_sqlbuild_model_names: tuple[str, ...],
    selected_dbt_unique_ids: tuple[str, ...],
) -> frozenset[DbtCombinedGraphKey]:
    return frozenset(
        (
            *(sqlbuild_model_graph_key(model_name) for model_name in selected_sqlbuild_model_names),
            *(dbt_model_graph_key(unique_id) for unique_id in selected_dbt_unique_ids),
        )
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
            destination=build_dbt_fingerprint_destination(project),
            warnings=warnings,
            query_sql=reuse_model.query_sql,
            version_hash_override=(
                reuse_write_version_hashes.get(dbt_graph_node_key(unique_id))
                or reuse_model.node_checksum
            ),
        )
    if warnings:
        report_progress(on_progress, message="; ".join(warnings))


def _write_defer_clone_dbt_node_source_watermarks(
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
    if project.effective_target_schema is None:
        return
    reuse_state_database: str | None
    reuse_state_schema: str | None
    reuse_state_database, reuse_state_schema = _reuse_state_location(
        reuse_manifest=reuse_manifest,
        unique_ids=unique_ids,
    )
    if reuse_state_schema is None:
        return
    successful_names: frozenset[str] = frozenset(
        item.name
        for item in result.item_results
        if item.status == CloneStatus.SUCCESS
        and item.action in {CloneAction.CLONED, CloneAction.COPIED}
    )
    if not successful_names:
        return
    reuse_records: NodeSourceWatermarkSet = _read_latest_node_source_watermarks_from_schema(
        adapter=adapter,
        connection=connection,
        database=reuse_state_database,
        schema=reuse_state_schema,
    )
    records: list[NodeSourceWatermarkRecord] = []
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
        reuse_record: NodeSourceWatermarkRecord | None = reuse_records.records.get(
            NodeSourceWatermarkIdentity(node_type=NODE_TYPE_DBT, node_name=unique_id)
        )
        if reuse_record is None:
            continue
        records.append(
            replace(
                reuse_record,
                target_database=current_model.database,
                target_schema=current_model.schema,
                target_name=current_model.alias or current_model.name,
                run_id=project.run_id,
                node_version_hash=reuse_record.node_version_hash,
                created_at=datetime.now(tz=UTC),
            )
        )
    if not records:
        return
    write_node_source_watermark_records(
        connection=connection,
        execute=adapter.execute,
        database=project.effective_target_database,
        schema=project.effective_target_schema,
        records=tuple(records),
        render_create_table_sql=adapter.render_create_node_source_watermark_table_sql,
        render_insert_records_sql=adapter.render_insert_node_source_watermark_records_sql,
    )
    report_progress(
        on_progress,
        message=f"Recorded dbt defer-clone node source watermarks ({len(records)}).",
    )


def _read_latest_node_source_watermarks_from_schema(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str
) -> NodeSourceWatermarkSet:
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=((database, schema, NODE_SOURCE_WATERMARK_TABLE_NAME),),
    )
    return read_latest_node_source_watermarks(
        connection=connection,
        execute=adapter.execute,
        table_exists=relation_lookup.exists(
            database=database,
            schema=schema,
            name=NODE_SOURCE_WATERMARK_TABLE_NAME,
        ),
        database=database,
        schema=schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_node_source_watermarks_sql,
    )


def _reuse_state_location(
    *, reuse_manifest: DbtManifestIndex, unique_ids: tuple[str, ...]
) -> tuple[str | None, str | None]:
    unique_id: str
    for unique_id in unique_ids:
        model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(unique_id)
        if model is not None and model.schema is not None:
            return model.database, model.schema
    return None, None
