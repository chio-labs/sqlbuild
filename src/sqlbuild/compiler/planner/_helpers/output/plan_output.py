"""PlanOutput assembly helpers."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMaterializationFile,
    DiscoveredProviderUsage,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.hooks.models import PythonHookEntry
from sqlbuild.compiler.planner._helpers.graph.loader_dag import upstream_loader_dependency_names
from sqlbuild.compiler.planner._helpers.graph.source_load_nodes import build_source_load_entries
from sqlbuild.compiler.planner._helpers.output.audit_entry import plan_audit
from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    build_model_materializations,
    extract_seed_columns,
    scope_overlaps,
)
from sqlbuild.compiler.planner._helpers.resolve.resolve import resolve_function_sql
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import plan_test
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    FunctionChangeResult,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerScope,
    PlanOutput,
    PlanOutputExtras,
    PlanProviderUsage,
    PlanWarning,
    SeedPlanEntry,
    SourceLoadPlanEntry,
    SqlTestPlanEntry,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.spec.contracts.models import SourceEntry


def build_plan_output(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    relations: PlannerRelationsContext,
    changes: PlannerChangeResults,
    model_entry_results: PlannerModelEntryResults,
    reload_sources: bool,
    extras: PlanOutputExtras | None = None,
) -> PlanOutput:
    resolved_extras: PlanOutputExtras = extras if extras is not None else PlanOutputExtras()
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (
        resolved_extras.dependency_baseline_entries
    )
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...] = (
        resolved_extras.existing_destination_input_entries
    )
    seed_version_hashes: dict[str, str] | None = resolved_extras.seed_version_hashes
    seed_metadata_jsons: dict[str, str] | None = resolved_extras.seed_metadata_jsons
    seed_plan_reasons: dict[str, PlanReason] | None = resolved_extras.seed_plan_reasons
    seed_entries: list[SeedPlanEntry] = [
        SeedPlanEntry(
            key=seed.key,
            name=seed.name,
            destination=seed.destination,
            file_path=seed.seed_file.file_path,
            columns=extract_seed_columns(seed),
            csv_settings=seed.schema_entry.csv_settings,
            fingerprint_definition=(seed_metadata_jsons or {}).get(seed.name, ""),
            fingerprint_version_hash=(seed_version_hashes or {}).get(seed.name, ""),
            fingerprint_metadata_json=(seed_metadata_jsons or {}).get(seed.name, "{}"),
            reason=_resolve_seed_plan_reason(
                seed_name=seed.name,
                expected_version_hash=(seed_version_hashes or {}).get(seed.name),
                snapshot=snapshot,
                seed_plan_reasons=seed_plan_reasons,
            ),
        )
        for seed in project.seeds
        if seed.key in scope.selected_keys
    ]
    source_load_entries: tuple[SourceLoadPlanEntry, ...] = build_source_load_entries(
        execution_order=scope.execution_order,
        selected_keys=scope.selected_keys,
        source_map=relations.source_map,
        is_reload=reload_sources,
    )
    _validate_skipped_intermediate_loader_targets(
        project=project,
        snapshot=snapshot,
        relations=relations,
        source_load_entries=source_load_entries,
    )
    function_entries: list[FunctionPlanEntry] = _build_function_entries(
        project=project,
        adapter=adapter,
        snapshot=snapshot,
        relations=relations,
        changes=changes,
        selected_keys=scope.selected_keys,
    )
    model_materializations: dict[str, str] = build_model_materializations(
        model_entry_results.entries
    )
    audit_entries: list[AuditPlanEntry] = _build_audit_entries(
        project=project,
        adapter=adapter,
        scope=scope,
        relations=relations,
        model_materializations=model_materializations,
    )
    test_entries: list[SqlTestPlanEntry]
    test_warnings: list[PlanWarning]
    test_entries, test_warnings = _build_test_entries(
        project=project,
        adapter=adapter,
        selected_keys=scope.selected_keys,
    )
    selected_test_keys: frozenset[CompiledObjectKey] = frozenset(
        entry.key for entry in test_entries
    )
    scoped_keys: frozenset[CompiledObjectKey] = scope.selected_keys | selected_test_keys
    scoped_order: tuple[CompiledObjectKey, ...] = tuple(
        k for k in scope.execution_order if k in scoped_keys
    )
    return PlanOutput(
        execution_order=scoped_order,
        model_entries=model_entry_results.entries,
        dependency_baseline_entries=dependency_baseline_entries,
        existing_destination_input_entries=existing_destination_input_entries,
        seed_entries=tuple(seed_entries),
        source_load_entries=tuple(source_load_entries),
        function_entries=tuple(function_entries),
        audit_entries=tuple(audit_entries),
        test_entries=tuple(test_entries),
        selected_keys=scope.selected_keys,
        warnings=(*model_entry_results.warnings, *test_warnings),
        upstream_deps=scope.upstream_deps,
        downstream_deps=scope.downstream_deps,
        model_locations=relations.model_locations,
        seed_locations=relations.seed_locations,
        function_locations=relations.function_locations,
        source_map=relations.source_map,
        source_read_map=relations.source_read_map,
        hook_functions=project.hook_functions,
        provider_usages=_build_provider_usages(
            project=project,
            model_entries=model_entry_results.entries,
            source_load_entries=source_load_entries,
        ),
        python_identity_fingerprints=snapshot.fingerprints.python_nodes,
    )


def _resolve_seed_plan_reason(
    *,
    seed_name: str,
    expected_version_hash: str | None,
    snapshot: WarehouseSnapshot,
    seed_plan_reasons: dict[str, PlanReason] | None = None,
) -> PlanReason:
    reason: PlanReason | None = (seed_plan_reasons or {}).get(seed_name)
    if reason is not None:
        return reason
    fingerprint: Fingerprint | None = snapshot.fingerprints.seeds.get(seed_name)
    if fingerprint is None:
        return PlanReason.FIRST_RUN
    if expected_version_hash is not None and fingerprint.version_hash != expected_version_hash:
        return PlanReason.CONFIG_CHANGED
    return PlanReason.NO_CHANGE


def _build_provider_usages(
    *,
    project: CompiledProject,
    model_entries: tuple[ModelPlanEntry, ...],
    source_load_entries: tuple[SourceLoadPlanEntry, ...],
) -> tuple[PlanProviderUsage, ...]:
    usages: list[PlanProviderUsage] = []
    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in project.loader_functions
    }
    source_load_entry: SourceLoadPlanEntry
    for source_load_entry in source_load_entries:
        loader: DiscoveredLoaderFunction | None = loader_by_name.get(source_load_entry.loader)
        if loader is None:
            continue
        usages.extend(
            _to_plan_provider_usages(
                provider_usages=loader.provider_usages,
                consumer_kind="loader",
                consumer_name=loader.name,
            )
        )

    hook_by_name: dict[str, DiscoveredHookFunction] = {
        hook.name: hook for hook in project.hook_functions
    }
    materialization_by_name: dict[str, DiscoveredMaterializationFile] = {
        materialization.name: materialization for materialization in project.materialization_files
    }
    model_entry: ModelPlanEntry
    for model_entry in model_entries:
        usages.extend(
            _hook_provider_usages(
                hook_entries=(model_entry.pre_hooks, model_entry.post_hooks),
                hook_by_name=hook_by_name,
            )
        )
        if model_entry.custom_materialization_name is None:
            continue
        materialization: DiscoveredMaterializationFile | None = materialization_by_name.get(
            model_entry.custom_materialization_name
        )
        if materialization is None:
            continue
        usages.extend(
            _to_plan_provider_usages(
                provider_usages=materialization.provider_usages,
                consumer_kind="custom materialization",
                consumer_name=materialization.name,
            )
        )
    return tuple(usages)


def _hook_provider_usages(
    *,
    hook_entries: tuple[object, ...],
    hook_by_name: dict[str, DiscoveredHookFunction],
) -> tuple[PlanProviderUsage, ...]:
    usages: list[PlanProviderUsage] = []
    hooks: list[object] = []
    hook_entry: object
    for hook_entry in hook_entries:
        if hook_entry is None:
            continue
        if isinstance(hook_entry, list | tuple):
            hooks.extend(hook_entry)
        else:
            hooks.append(hook_entry)
    hook: object
    for hook in hooks:
        if not isinstance(hook, PythonHookEntry):
            continue
        discovered_hook: DiscoveredHookFunction | None = hook_by_name.get(hook.name)
        if discovered_hook is None:
            continue
        usages.extend(
            _to_plan_provider_usages(
                provider_usages=discovered_hook.provider_usages,
                consumer_kind="hook",
                consumer_name=discovered_hook.name,
            )
        )
    return tuple(usages)


def _to_plan_provider_usages(
    *,
    provider_usages: tuple[DiscoveredProviderUsage, ...],
    consumer_kind: str,
    consumer_name: str,
) -> tuple[PlanProviderUsage, ...]:
    return tuple(
        PlanProviderUsage(
            provider_name=usage.provider_name,
            consumer_kind=consumer_kind,
            consumer_name=consumer_name,
            parameter_name=usage.parameter_name,
            annotation_class_name=usage.annotation_class_name,
            annotation_module=usage.annotation_module,
        )
        for usage in provider_usages
    )


def _validate_skipped_intermediate_loader_targets(
    *,
    project: CompiledProject,
    snapshot: WarehouseSnapshot,
    relations: PlannerRelationsContext,
    source_load_entries: tuple[SourceLoadPlanEntry, ...],
) -> None:
    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in project.loader_functions
    }
    selected_load_names: frozenset[str] = frozenset(entry.name for entry in source_load_entries)
    entry: SourceLoadPlanEntry
    for entry in source_load_entries:
        source_entry: SourceEntry | None = relations.source_map.get(entry.name)
        if source_entry is None or source_entry.loader is None:
            continue
        loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(source_entry.loader)
        if loader_function is None:
            continue
        dependency_loader_name: str
        for dependency_loader_name in upstream_loader_dependency_names(
            loader_function=loader_function,
            loader_functions=project.loader_functions,
        ):
            dependency_source: SourceEntry | None = relations.source_map.get(dependency_loader_name)
            if dependency_source is None or dependency_source.name in selected_load_names:
                continue
            dependency_target: str = dependency_source.table or dependency_source.name
            if dependency_target in snapshot.existing_relations:
                continue
            raise PlannerInputError(
                f"Source '{source_entry.name}' requires intermediate loader "
                f"'{dependency_loader_name}', but its target relation "
                f"'{dependency_target}' does not exist; use +source:{source_entry.name} "
                "to refresh upstream ingress dependencies"
            )


def _build_function_entries(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    snapshot: WarehouseSnapshot,
    relations: PlannerRelationsContext,
    changes: PlannerChangeResults,
    selected_keys: frozenset[CompiledObjectKey],
) -> list[FunctionPlanEntry]:
    entries: list[FunctionPlanEntry] = []
    function: CompiledFunction
    for function in project.functions:
        if function.key not in selected_keys:
            continue
        function_change: FunctionChangeResult = changes.functions[function.name]
        entries.append(
            FunctionPlanEntry(
                key=function.key,
                name=function.name,
                relative_path=function.relative_path,
                destination=function.destination,
                arguments=function.arguments,
                returns=function.returns,
                body_sql=resolve_function_sql(
                    adapter=adapter,
                    function=function,
                    model_locations=relations.model_locations,
                    seed_locations=relations.seed_locations,
                    function_locations=relations.function_locations,
                    source_map=relations.source_read_map,
                    source_warehouse_columns=relations.source_warehouse_columns,
                    star_exclude_keyword=relations.star_exclude_keyword,
                ),
                fingerprint_query_sql=function_change.fingerprint_sql,
                fingerprint_destination=function.fingerprint_destination,
                return_columns=function.return_columns,
                language=function.language,
                source_file_path=function.source_file_path,
                runtime_version=function.runtime_version,
                entry_point=function.entry_point,
                packages=function.packages,
                previous_query_sql=(
                    snapshot.fingerprints.functions[function.name].definition
                    if function.name in snapshot.fingerprints.functions
                    else None
                ),
                reason=function_change.reason,
                backfill=function_change.backfill,
            )
        )
    return entries


def _build_audit_entries(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    model_materializations: dict[str, str],
) -> list[AuditPlanEntry]:
    entries: list[AuditPlanEntry] = []
    audit: CompiledAudit
    for audit in project.audits:
        if not scope_overlaps(scope_deps=audit.scope_deps, selected_keys=scope.selected_keys):
            continue
        entries.append(
            plan_audit(
                audit=audit,
                model_locations=relations.model_locations,
                seed_locations=relations.seed_locations,
                source_map=relations.source_read_map,
                adapter=adapter,
                upstream_deps=scope.upstream_deps,
                downstream_deps=scope.downstream_deps,
                model_materializations=model_materializations,
            )
        )
    return entries


def _build_test_entries(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    selected_keys: frozenset[CompiledObjectKey],
) -> tuple[list[SqlTestPlanEntry], list[PlanWarning]]:
    entries: list[SqlTestPlanEntry] = []
    warnings: list[PlanWarning] = []
    sql_test: CompiledSqlTest
    for sql_test in project.sql_tests:
        if not scope_overlaps(scope_deps=sql_test.scope_deps, selected_keys=selected_keys):
            continue
        test_entry: SqlTestPlanEntry
        test_warnings: tuple[PlanWarning, ...]
        test_entry, test_warnings = plan_test(
            test=sql_test,
            project=project,
            adapter=adapter,
            sql_analysis_enabled=project.settings.sql_analysis,
        )
        entries.append(test_entry)
        warnings.extend(test_warnings)
    return entries, warnings
