"""PlanOutput assembly helpers."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledFunction,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.models.sql_tests import CompiledSqlTest
from sqlbuild.compiler.planner.helpers.audit_entry import plan_audit
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_model_materializations,
    extract_seed_columns,
    scope_overlaps,
)
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_function_sql
from sqlbuild.compiler.planner.helpers.source_load_nodes import build_source_load_entries
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    FunctionChangeResult,
    FunctionPlanEntry,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerScope,
    PlanOutput,
    PlanWarning,
    SeedPlanEntry,
    SourceLoadPlanEntry,
    SqlTestPlanEntry,
    WarehouseSnapshot,
)


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
) -> PlanOutput:
    seed_entries: list[SeedPlanEntry] = [
        SeedPlanEntry(
            key=seed.key,
            name=seed.name,
            target=seed.target,
            file_path=seed.seed_file.file_path,
            columns=extract_seed_columns(seed),
            csv_settings=seed.schema_entry.csv_settings,
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
        seed_entries=tuple(seed_entries),
        source_load_entries=tuple(source_load_entries),
        function_entries=tuple(function_entries),
        audit_entries=tuple(audit_entries),
        test_entries=tuple(test_entries),
        selected_keys=scope.selected_keys,
        warnings=(*model_entry_results.warnings, *test_warnings),
        upstream_deps=scope.upstream_deps,
        downstream_deps=scope.downstream_deps,
        model_targets=relations.model_targets,
        seed_targets=relations.seed_targets,
        function_targets=relations.function_targets,
        source_map=relations.source_map,
        source_read_map=relations.source_read_map,
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
                target=function.target,
                arguments=function.arguments,
                returns=function.returns,
                body_sql=resolve_function_sql(
                    adapter=adapter,
                    function=function,
                    model_targets=relations.model_targets,
                    seed_targets=relations.seed_targets,
                    function_targets=relations.function_targets,
                    source_map=relations.source_read_map,
                    source_warehouse_columns=relations.source_warehouse_columns,
                    star_exclude_keyword=relations.star_exclude_keyword,
                ),
                fingerprint_query_sql=function_change.fingerprint_sql,
                fingerprint_target=function.fingerprint_target,
                return_columns=function.return_columns,
                language=function.language,
                source_file_path=function.source_file_path,
                runtime_version=function.runtime_version,
                entry_point=function.entry_point,
                packages=function.packages,
                previous_query_sql=(
                    snapshot.fingerprints[function.name].query_sql
                    if function.name in snapshot.fingerprints
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
        if not scope_overlaps(audit.scope_deps, scope.selected_keys):
            continue
        entries.append(
            plan_audit(
                audit=audit,
                model_targets=relations.model_targets,
                seed_targets=relations.seed_targets,
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
        if not scope_overlaps(sql_test.scope_deps, selected_keys):
            continue
        test_entry: SqlTestPlanEntry
        test_warnings: tuple[PlanWarning, ...]
        test_entry, test_warnings = plan_test(
            test=sql_test,
            project=project,
            adapter=adapter,
            sqlglot_enabled=project.settings.sqlglot,
        )
        entries.append(test_entry)
        warnings.extend(test_warnings)
    return entries, warnings
