"""SQLBuild plan output helpers for dbt interop pipelines."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.display_plan import build_display_only_sqlbuild_plan
from sqlbuild.compiler.planner.main.planning.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    DeferralInputs,
    DependencyBaselinePlanEntry,
    GraphNodeKey,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import StandardScopePruning
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.integrations.dbt.constants import DBT_MATERIALIZATION_VIEW
from sqlbuild.integrations.dbt.helpers.manifest.core import dbt_manifest_model_materialization
from sqlbuild.integrations.dbt.helpers.manifest.sqlbuild_refs import (
    resolve_sqlbuild_model_dbt_refs,
)
from sqlbuild.integrations.dbt.helpers.planning.graph_projection import (
    dbt_graph_node_key,
    dbt_source_graph_node_key,
    sqlbuild_model_graph_node_key,
)
from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    build_dbt_model_planning_result,
)
from sqlbuild.integrations.dbt.helpers.selection.sql_test_targets import (
    adapt_project_for_dbt_sql_tests,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtCommandResult,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtCombinedGraphResourceType
from sqlbuild.shared.models import RelationLookup


def dbt_failure_detail(result: DbtCommandResult) -> str | None:
    detail: str = (result.stderr or result.stdout).strip()
    return detail or None


def find_sqlbuild_models_with_missing_dbt_relations(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    adapter: BaseAdapter,
    connection: object,
    selected_model_names: tuple[str, ...],
    dbt_unique_ids_selected_for_execution: frozenset[str],
) -> dict[str, tuple[DbtManifestModel, ...]]:
    """Return selected SQLBuild models blocked by absent, unselected dbt refs."""

    candidates: list[tuple[str, DbtManifestModel]] = []
    for model, dbt_model in resolve_sqlbuild_model_dbt_refs(
        project=project,
        manifest=manifest,
        selected_model_names=selected_model_names,
    ):
        if dbt_model.unique_id in dbt_unique_ids_selected_for_execution:
            continue
        candidates.append((model.name, dbt_model))
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (dbt_model.database, dbt_model.schema, dbt_model.alias or dbt_model.name)
            for _, dbt_model in candidates
        ),
    )
    blocked: dict[str, list[DbtManifestModel]] = {}
    for model_name, dbt_model in candidates:
        if relation_lookup.exists(
            database=dbt_model.database,
            schema=dbt_model.schema,
            name=dbt_model.alias or dbt_model.name,
        ):
            continue
        blocked.setdefault(model_name, []).append(dbt_model)
    return {name: tuple(models) for name, models in blocked.items()}


def find_direct_dbt_dependency_unique_ids(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_model_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return direct dbt refs needed by selected SQLBuild models."""

    unique_ids: set[str] = set()
    for _model, dbt_model in resolve_sqlbuild_model_dbt_refs(
        project=project,
        manifest=manifest,
        selected_model_names=selected_model_names,
    ):
        unique_ids.add(dbt_model.unique_id)
    return tuple(sorted(unique_ids))


def build_sqlbuild_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    adapter: BaseAdapter,
    adapter_name: str,
    selected_model_names: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
    forced_stale_model_names: tuple[str, ...] = (),
    external_blocked_model_names: tuple[str, ...] = (),
    sqlbuild_args: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
    deferred_relations: dict[str, RelationInfo] | None = None,
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (),
    disable_scope_pruning: bool = False,
    manifest: DbtManifestIndex | None = None,
    dbt_manifest: DbtManifestIndex | None = None,
    dbt_graph: DbtCombinedGraph | None = None,
    dbt_source_freshness: StandardSourceFreshnessPlanningResult | None = None,
) -> PlanOutput | None:
    if not selected_model_names:
        return None
    cursor_overrides: CursorOverrides = _parse_cursor_overrides(sqlbuild_args)
    planning_project: CompiledProject = (
        project
        if manifest is None
        else adapt_project_for_dbt_sql_tests(
            project=project,
            manifest=manifest,
            target_names=selected_model_names,
        )
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        try:
            plan_output: PlanOutput = build_execution_plan(
                project=planning_project,
                adapter=adapter,
                connection=connection,
                selection=PlannerSelection(select=selected_model_names),
                overrides=PlannerOverrides(
                    cursor_overrides=cursor_overrides,
                    full_refresh="--full-refresh" in sqlbuild_args,
                    forced_stale_model_names=forced_stale_model_names,
                    external_blocked_model_names=external_blocked_model_names,
                ),
                deferral=DeferralInputs(deferred_relations=deferred_relations),
                policies=PlannerPolicies(
                    standard_scope_pruning=(
                        StandardScopePruning.PRUNE_UNCHANGED
                        if "--force" not in sqlbuild_args and not disable_scope_pruning
                        else StandardScopePruning.NONE
                    ),
                ),
                on_progress=on_progress,
            )
            return replace(
                plan_output,
                dependency_baseline_entries=(
                    *dependency_baseline_entries,
                    *plan_output.dependency_baseline_entries,
                ),
                source_freshness=_merged_source_freshness(
                    native=plan_output.source_freshness,
                    dbt=dbt_source_freshness,
                ),
                **_dbt_node_source_watermark_graph_kwargs(
                    project=project,
                    selected_model_names=selected_model_names,
                    required_dbt_unique_ids=required_dbt_unique_ids,
                    manifest=dbt_manifest,
                    graph=dbt_graph,
                ),
            )
        except PlannerInputError:
            return build_display_only_sqlbuild_plan(
                project=planning_project,
                selected_model_names=selected_model_names,
                full_refresh="--full-refresh" in sqlbuild_args,
            )
    finally:
        adapter.close(connection)


def build_dbt_model_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    adapter: BaseAdapter,
    adapter_name: str,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None = None,
    candidate_unique_ids: tuple[str, ...],
    selected_unique_ids: tuple[str, ...],
    full_refresh: bool = False,
    force: bool = False,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
    on_progress: Callable[[str], None] | None = None,
) -> DbtModelPlanningResult | None:
    if not candidate_unique_ids:
        return None
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        planning_start: float = time.monotonic()
        report_progress(
            on_progress,
            "Inspecting dbt model state: checking warehouse relations and fingerprints...",
        )
        result: DbtModelPlanningResult = build_dbt_model_planning_result(
            manifest=manifest,
            candidate_unique_ids=candidate_unique_ids,
            selected_unique_ids=selected_unique_ids,
            project=project,
            graph=graph,
            full_refresh=full_refresh,
            force=force,
            adapter=adapter,
            connection=connection,
        )
        report_progress(
            on_progress,
            f"Inspected dbt model state. ({time.monotonic() - planning_start:.2f}s)",
        )
        return result
    finally:
        adapter.close(connection)


def _dbt_node_source_watermark_graph_kwargs(
    *,
    project: CompiledProject,
    selected_model_names: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
    manifest: DbtManifestIndex | None,
    graph: DbtCombinedGraph | None,
) -> dict[str, object]:
    if manifest is None or graph is None:
        return {}
    direct_refs: tuple[tuple[object, DbtManifestModel], ...] = resolve_sqlbuild_model_dbt_refs(
        project=project,
        manifest=manifest,
        selected_model_names=selected_model_names,
    )
    node_keys: set[GraphNodeKey] = set()
    materialized_node_keys: set[GraphNodeKey] = set()
    upstream_deps: dict[GraphNodeKey, list[GraphNodeKey]] = {}
    source_identities_by_key: dict[GraphNodeKey, SourceFreshnessIdentity] = {}
    _model: object
    dbt_model: DbtManifestModel
    for _model, dbt_model in direct_refs:
        model_key: GraphNodeKey = sqlbuild_model_graph_node_key(_model.name)
        upstream_deps.setdefault(model_key, []).append(dbt_graph_node_key(dbt_model.unique_id))
    for unique_id in required_dbt_unique_ids:
        _add_dbt_watermark_subgraph(
            unique_id=unique_id,
            manifest=manifest,
            graph=graph,
            node_keys=node_keys,
            materialized_node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            source_identities_by_key=source_identities_by_key,
        )
    for _model, dbt_model in direct_refs:
        _add_dbt_watermark_subgraph(
            unique_id=dbt_model.unique_id,
            manifest=manifest,
            graph=graph,
            node_keys=node_keys,
            materialized_node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            source_identities_by_key=source_identities_by_key,
        )
    return {
        "node_source_watermark_node_keys": frozenset(node_keys),
        "node_source_watermark_materialized_node_keys": frozenset(materialized_node_keys),
        "node_source_watermark_upstream_deps": {
            key: tuple(dict.fromkeys(values)) for key, values in upstream_deps.items()
        },
        "node_source_watermark_source_identities_by_key": source_identities_by_key,
    }


def _add_dbt_watermark_subgraph(
    *,
    unique_id: str,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    node_keys: set[GraphNodeKey],
    materialized_node_keys: set[GraphNodeKey],
    upstream_deps: dict[GraphNodeKey, list[GraphNodeKey]],
    source_identities_by_key: dict[GraphNodeKey, SourceFreshnessIdentity],
) -> None:
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is None:
        return
    key: GraphNodeKey = dbt_graph_node_key(unique_id)
    if key in node_keys:
        return
    node_keys.add(key)
    if dbt_manifest_model_materialization(model=model) != DBT_MATERIALIZATION_VIEW:
        materialized_node_keys.add(key)
    combined_key: DbtCombinedGraphKey = DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name=unique_id,
    )
    upstream_key: DbtCombinedGraphKey
    for upstream_key in graph.upstream_deps.get(combined_key, ()):
        if upstream_key.owner != DbtCombinedGraphOwner.DBT:
            continue
        if upstream_key.resource_type == DbtCombinedGraphResourceType.MODEL:
            upstream_graph_key: GraphNodeKey = dbt_graph_node_key(upstream_key.name)
            upstream_deps.setdefault(key, []).append(upstream_graph_key)
            _add_dbt_watermark_subgraph(
                unique_id=upstream_key.name,
                manifest=manifest,
                graph=graph,
                node_keys=node_keys,
                materialized_node_keys=materialized_node_keys,
                upstream_deps=upstream_deps,
                source_identities_by_key=source_identities_by_key,
            )
            continue
        if upstream_key.resource_type == DbtCombinedGraphResourceType.SOURCE:
            source: DbtManifestSource | None = manifest.sources_by_unique_id.get(upstream_key.name)
            if source is None:
                continue
            source_key: GraphNodeKey = dbt_source_graph_node_key(source.unique_id)
            node_keys.add(source_key)
            upstream_deps.setdefault(key, []).append(source_key)
            source_identities_by_key[source_key] = _dbt_source_identity(source)


def _dbt_source_identity(source: DbtManifestSource) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=source.unique_id,
        target_database=source.database,
        target_schema=source.schema,
        target_name=source.identifier or source.name,
    )


def _merged_source_freshness(
    *,
    native: StandardSourceFreshnessPlanningResult | None,
    dbt: StandardSourceFreshnessPlanningResult | None,
) -> StandardSourceFreshnessPlanningResult | None:
    if native is None:
        return dbt
    if dbt is None:
        return native
    records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in native.observed_records
    }
    record: SourceFreshnessRecord
    for record in dbt.observed_records:
        records_by_identity[record.identity] = record
    return replace(native, observed_records=tuple(records_by_identity.values()))


def _parse_cursor_overrides(args: tuple[str, ...]) -> CursorOverrides:
    return CursorOverrides(
        start_ts=_parse_value(args, "--start-cursor-ts"),
        end_ts=_parse_value(args, "--end-cursor-ts"),
        start_int=_parse_value(args, "--start-cursor-int"),
        end_int=_parse_value(args, "--end-cursor-int"),
    )


def _parse_value(args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]
