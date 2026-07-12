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
    DbtInteropCompiledProject,
    DbtInteropPlan,
    DbtModelPlanningResult,
    DbtPlanEnvironment,
    DbtSqlbuildPlanArtifacts,
    DbtSqlbuildPlanRequest,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    append_stale_out_of_selection_warning,
    build_dbt_non_model_run_unique_ids,
    build_dbt_pruned_seed_unique_ids,
    build_dbt_pruned_test_unique_ids,
    build_unblocked_sqlbuild_model_names,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
)
from sqlbuild.shared.models import ConnectionHooks, RelationLookup
from sqlbuild.shared.types import ConnectionElapsedCallback


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
    environment: DbtPlanEnvironment,
    request: DbtSqlbuildPlanRequest,
    hooks: ConnectionHooks,
) -> PlanOutput | None:
    project_dir: Path = environment.project_dir
    discovered_inputs: DiscoveredProjectInputs = environment.discovered_inputs
    project: CompiledProject = environment.project
    adapter: BaseAdapter = environment.adapter
    adapter_name: str = environment.adapter_name
    selected_model_names: tuple[str, ...] = request.selected_model_names
    required_dbt_unique_ids: tuple[str, ...] = request.required_dbt_unique_ids
    sqlbuild_args: tuple[str, ...] = request.sqlbuild_args
    forced_stale_model_names: tuple[str, ...] = request.forced_stale_model_names
    external_blocked_model_names: tuple[str, ...] = request.external_blocked_model_names
    deferred_relations: dict[str, RelationInfo] | None = request.deferred_relations
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (
        request.dependency_baseline_entries
    )
    disable_scope_pruning: bool = request.disable_scope_pruning
    manifest: DbtManifestIndex | None = request.artifacts.manifest
    dbt_manifest: DbtManifestIndex | None = request.artifacts.dbt_manifest
    dbt_graph: DbtCombinedGraph | None = request.artifacts.dbt_graph
    dbt_source_freshness: StandardSourceFreshnessPlanningResult | None = (
        request.artifacts.dbt_source_freshness
    )
    on_progress: Callable[[str], None] | None = hooks.on_progress
    on_connection_start: Callable[[int], None] | None = hooks.on_connection_start
    on_connection_complete: ConnectionElapsedCallback | None = hooks.on_connection_complete
    on_connection_error: ConnectionElapsedCallback | None = hooks.on_connection_error
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
            on_connection_error(connection_count=1, elapsed_seconds=time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(connection_count=1, elapsed_seconds=time.monotonic() - start)
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
    environment: DbtPlanEnvironment,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None = None,
    candidate_unique_ids: tuple[str, ...],
    selected_unique_ids: tuple[str, ...],
    full_refresh: bool = False,
    force: bool = False,
    hooks: ConnectionHooks,
) -> DbtModelPlanningResult | None:
    project_dir: Path = environment.project_dir
    discovered_inputs: DiscoveredProjectInputs = environment.discovered_inputs
    project: CompiledProject = environment.project
    adapter: BaseAdapter = environment.adapter
    adapter_name: str = environment.adapter_name
    on_connection_start: Callable[[int], None] | None = hooks.on_connection_start
    on_connection_complete: ConnectionElapsedCallback | None = hooks.on_connection_complete
    on_connection_error: ConnectionElapsedCallback | None = hooks.on_connection_error
    on_progress: Callable[[str], None] | None = hooks.on_progress
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
            on_connection_error(connection_count=1, elapsed_seconds=time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(connection_count=1, elapsed_seconds=time.monotonic() - start)
    try:
        planning_start: float = time.monotonic()
        report_progress(
            on_progress=on_progress,
            message="Inspecting dbt model state: checking warehouse relations and fingerprints...",
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
            on_progress=on_progress,
            message=f"Inspected dbt model state. ({time.monotonic() - planning_start:.2f}s)",
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
        node_keys, materialized_node_keys, upstream_deps, source_identities_by_key = (
            _add_dbt_watermark_subgraph(
                unique_id=dbt_model.unique_id,
                manifest=manifest,
                graph=graph,
                node_keys=node_keys,
                materialized_node_keys=materialized_node_keys,
                upstream_deps=upstream_deps,
                source_identities_by_key=source_identities_by_key,
            )
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
) -> tuple[
    set[GraphNodeKey],
    set[GraphNodeKey],
    dict[GraphNodeKey, list[GraphNodeKey]],
    dict[GraphNodeKey, SourceFreshnessIdentity],
]:
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is None:
        return node_keys, materialized_node_keys, upstream_deps, source_identities_by_key
    key: GraphNodeKey = dbt_graph_node_key(unique_id)
    if key in node_keys:
        return node_keys, materialized_node_keys, upstream_deps, source_identities_by_key
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
            node_keys, materialized_node_keys, upstream_deps, source_identities_by_key = (
                _add_dbt_watermark_subgraph(
                    unique_id=upstream_key.name,
                    manifest=manifest,
                    graph=graph,
                    node_keys=node_keys,
                    materialized_node_keys=materialized_node_keys,
                    upstream_deps=upstream_deps,
                    source_identities_by_key=source_identities_by_key,
                )
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
    return node_keys, materialized_node_keys, upstream_deps, source_identities_by_key


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
        start_ts=_parse_value(args=args, flag="--start-cursor-ts"),
        end_ts=_parse_value(args=args, flag="--end-cursor-ts"),
        start_int=_parse_value(args=args, flag="--start-cursor-int"),
        end_int=_parse_value(args=args, flag="--end-cursor-int"),
    )


def _parse_value(*, args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _connection_progress_hooks(
    *,
    connection_progress: Any | None,
    on_progress: Callable[[str], None] | None,
) -> ConnectionHooks:
    if connection_progress is None:
        return ConnectionHooks(on_progress=on_progress)
    return ConnectionHooks(
        on_progress=on_progress,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
    )


def attach_dbt_model_plan(
    *,
    plan: DbtInteropPlan,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    full_refresh: bool,
    force: bool,
    connection_progress: Any | None,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropPlan:
    """Attach dbt model planning output and stale-selection warnings to the plan."""

    dbt_model_plan: DbtModelPlanningResult | None = build_dbt_model_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        manifest=manifest,
        graph=graph,
        candidate_unique_ids=tuple(
            sorted(
                frozenset(
                    (
                        *plan.dbt_selected_unique_ids,
                        *plan.selection.dbt_required_unique_ids,
                    )
                )
            )
        ),
        selected_unique_ids=plan.dbt_selected_unique_ids,
        full_refresh=full_refresh,
        force=force,
        hooks=_connection_progress_hooks(
            connection_progress=connection_progress, on_progress=on_progress
        ),
    )
    if dbt_model_plan is None:
        return plan
    updated_plan: DbtInteropPlan = replace(plan, dbt_model_plan=dbt_model_plan)
    return append_stale_out_of_selection_warning(plan=updated_plan, dbt_model_plan=dbt_model_plan)


def apply_dbt_build_pruning(plan: DbtInteropPlan) -> DbtInteropPlan:
    """Attach non-model run ids and pruned seed/test ids for build execution."""

    return replace(
        plan,
        dbt_non_model_run_unique_ids=build_dbt_non_model_run_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
        dbt_pruned_seed_unique_ids=build_dbt_pruned_seed_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
        dbt_pruned_test_unique_ids=build_dbt_pruned_test_unique_ids(
            command=DbtInteropCommand.BUILD,
            plan=plan,
        ),
    )


def attach_sqlbuild_plan_output(
    *,
    plan: DbtInteropPlan,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    sqlbuild_args: tuple[str, ...],
    connection_progress: Any | None,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropPlan:
    """Attach the SQLBuild-side plan output to the interop plan when present."""

    sqlbuild_plan_output: PlanOutput | None = build_sqlbuild_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        request=DbtSqlbuildPlanRequest(
            selected_model_names=build_unblocked_sqlbuild_model_names(plan),
            required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
            sqlbuild_args=sqlbuild_args,
            forced_stale_model_names=(
                plan.dbt_model_plan.stale_sqlbuild_model_names
                if plan.dbt_model_plan is not None
                else ()
            ),
            dependency_baseline_entries=(),
            artifacts=DbtSqlbuildPlanArtifacts(
                dbt_manifest=manifest,
                dbt_graph=graph,
                dbt_source_freshness=(
                    plan.dbt_model_plan.source_freshness
                    if plan.dbt_model_plan is not None
                    else None
                ),
            ),
        ),
        hooks=_connection_progress_hooks(
            connection_progress=connection_progress, on_progress=on_progress
        ),
    )
    if sqlbuild_plan_output is None:
        return plan
    return replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)
