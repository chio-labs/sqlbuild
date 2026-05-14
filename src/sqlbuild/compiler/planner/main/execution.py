"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompiledSqlTest,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.audit_entry import plan_audit
from sqlbuild.compiler.planner.helpers.buildability import check_buildability
from sqlbuild.compiler.planner.helpers.cascade import build_self_cascade, resolve_cascade
from sqlbuild.compiler.planner.helpers.function_fingerprints import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_model_materializations,
    build_path_index,
    build_tag_index,
    extract_seed_columns,
    gather_source_columns,
    plan_model,
    resolve_cursor_overrides,
    scope_overlaps,
)
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    apply_deferred_targets,
    build_function_targets,
    build_model_targets,
    build_seed_targets,
)
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_function_sql
from sqlbuild.compiler.planner.helpers.selectors import resolve_selectors
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    BackfillResult,
    CascadeResult,
    CursorOverrides,
    FunctionPlanEntry,
    MissingUpstream,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SeedPlanEntry,
    SqlTestPlanEntry,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason
from sqlbuild.shared.types import ExternalReferenceResolver
from sqlbuild.spec.models.source import SourceEntry


def build_execution_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    on_progress: Callable[[str], None] | None = None,
    deferred_targets: dict[str, CompiledRelationTarget] | None = None,
    deferred_relations: dict[str, RelationInfo] | None = None,
) -> PlanOutput:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = _build_all_keys(project)
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    tag_index: dict[str, frozenset[CompiledObjectKey]] = build_tag_index(project)
    path_idx: dict[CompiledObjectKey, str] = build_path_index(project)

    selected_keys: frozenset[CompiledObjectKey] = resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=tag_index,
        path_index=path_idx,
    )

    execution_order: tuple[CompiledObjectKey, ...] = topologically_order_keys(upstream_deps)
    external_reference_resolver: ExternalReferenceResolver | None = (
        project.external_reference_resolver
    )

    execute: Any = adapter.execute
    warehouse_start: float = time.monotonic()
    if on_progress is not None:
        on_progress("Inspecting warehouse state...")
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        selected_keys=selected_keys,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        on_progress=on_progress,
        deferred_targets=deferred_targets,
    )

    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=selected_keys,
        upstream_deps=upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferred_relations,
    )
    if missing:
        names: str = ", ".join(m.key.name for m in missing[:5])
        raise PlannerInputError(
            f"cannot build selected scope: {len(missing)} missing upstream dependencies ({names})",
            code="S301",
        )

    model_targets: dict[str, CompiledRelationTarget] = build_model_targets(project.models)
    seed_targets: dict[str, CompiledRelationTarget] = build_seed_targets(project.seeds)
    function_targets: dict[str, CompiledRelationTarget] = build_function_targets(project.functions)
    if deferred_targets is not None:
        apply_deferred_targets(
            model_targets=model_targets,
            seed_targets=seed_targets,
            deferred_targets=deferred_targets,
            selected_keys=selected_keys,
        )
    source_map: dict[str, SourceEntry] = {
        s.source_entry.name: s.source_entry for s in project.sources
    }
    star_exclude_keyword: str = adapter.star_exclude_keyword()
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = gather_source_columns(
        project=project, adapter=adapter, connection=connection
    )
    if on_progress is not None:
        on_progress(f"Inspected warehouse state. ({time.monotonic() - warehouse_start:.2f}s)")
        on_progress("Generating plan...")
    plan_start: float = time.monotonic()

    sqlglot_enabled: bool = project.settings.sqlglot
    query_change_tracking: bool = project.settings.query_change_tracking

    model_entries: list[ModelPlanEntry] = []
    all_warnings: list[PlanWarning] = []
    effective_cascades: dict[str, CascadeResult] = {}
    model_cursor_types: dict[str, str | None] = {}

    function_fingerprint_sql: dict[str, str] = {}
    function_reasons: dict[str, PlanReason] = {}
    function_backfills: dict[str, BackfillResult] = {}
    function: CompiledFunction
    for function in project.functions:
        fingerprint_sql: str = build_compiled_function_fingerprint_sql(function)
        function_fingerprint_sql[function.name] = fingerprint_sql
        if function.key not in selected_keys:
            continue
        function_reason: PlanReason
        function_backfill: BackfillResult
        function_reason, function_backfill = detect_function_change(
            function=function,
            fingerprint_sql=fingerprint_sql,
            snapshot=snapshot,
            query_change_tracking=query_change_tracking,
            full_refresh=full_refresh,
        )
        function_reasons[function.name] = function_reason
        function_backfills[function.name] = function_backfill
        effective_cascades[function.name] = build_self_cascade(
            function_backfill,
            root_cause=function.name,
            root_reason=function_reason,
        )

    key: CompiledObjectKey
    for key in execution_order:
        if key not in selected_keys:
            continue
        if key.resource_type != CompiledResourceType.MODEL:
            continue

        model: CompiledModel | None = _find_model(project, key.name)
        if model is None:
            continue

        resolved_start: str | None
        resolved_end: str | None
        resolved_start, resolved_end = resolve_cursor_overrides(
            model=model,
            cursor_overrides=cursor_overrides,
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
        )
        entry: ModelPlanEntry
        warnings: tuple[PlanWarning, ...]
        entry, warnings = plan_model(
            model=model,
            snapshot=snapshot,
            adapter=adapter,
            model_targets=model_targets,
            models_by_name=models_by_name,
            seed_targets=seed_targets,
            function_targets=function_targets,
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            star_exclude_keyword=star_exclude_keyword,
            sqlglot_enabled=sqlglot_enabled,
            query_change_tracking=query_change_tracking,
            full_refresh=full_refresh,
            start_cursor_override=resolved_start,
            end_cursor_override=resolved_end,
            external_reference_resolver=external_reference_resolver,
        )

        model_cursor_types[entry.name] = entry.cursor_type
        cascade: CascadeResult | None = resolve_cascade(
            model_name=entry.name,
            own_backfill=entry.backfill,
            own_cursor_type=entry.cursor_type,
            upstream_keys=upstream_deps.get(key, ()),
            effective_cascades=effective_cascades,
            model_cursor_types=model_cursor_types,
        )
        if cascade is not None:
            entry, warnings = plan_model(
                model=model,
                snapshot=snapshot,
                adapter=adapter,
                model_targets=model_targets,
                models_by_name=models_by_name,
                seed_targets=seed_targets,
                function_targets=function_targets,
                source_map=source_map,
                source_warehouse_columns=source_warehouse_columns,
                star_exclude_keyword=star_exclude_keyword,
                sqlglot_enabled=sqlglot_enabled,
                query_change_tracking=query_change_tracking,
                full_refresh=full_refresh,
                start_cursor_override=resolved_start,
                end_cursor_override=resolved_end,
                backfill_override=BackfillResult(
                    action=cascade.effective_action,
                    duration=cascade.effective_duration,
                ),
                external_reference_resolver=external_reference_resolver,
            )
            entry = replace(entry, cascade=cascade)
            effective_cascades[entry.name] = cascade
        else:
            effective_cascades[entry.name] = build_self_cascade(
                entry.backfill,
                root_cause=entry.name,
                root_reason=entry.reason,
            )

        model_entries.append(entry)
        all_warnings.extend(warnings)

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
        if seed.key in selected_keys
    ]

    function_entries: list[FunctionPlanEntry] = [
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
                model_targets=model_targets,
                seed_targets=seed_targets,
                function_targets=function_targets,
                source_map=source_map,
                source_warehouse_columns=source_warehouse_columns,
                star_exclude_keyword=star_exclude_keyword,
            ),
            fingerprint_query_sql=function_fingerprint_sql[function.name],
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
            reason=function_reasons.get(function.name, PlanReason.NO_CHANGE),
            backfill=function_backfills.get(
                function.name, BackfillResult(action=BackfillAction.WARN_ONLY)
            ),
        )
        for function in project.functions
        if function.key in selected_keys
    ]

    model_materializations: dict[str, str] = build_model_materializations(tuple(model_entries))

    audit_entries: list[AuditPlanEntry] = []
    audit: CompiledAudit
    for audit in project.audits:
        if not scope_overlaps(audit.scope_deps, selected_keys):
            continue
        audit_entries.append(
            plan_audit(
                audit=audit,
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
                upstream_deps=upstream_deps,
                downstream_deps=downstream_deps,
                model_materializations=model_materializations,
            )
        )

    test_entries: list[SqlTestPlanEntry] = []
    sql_test: CompiledSqlTest
    for sql_test in project.sql_tests:
        if not scope_overlaps(sql_test.scope_deps, selected_keys):
            continue
        test_entry: SqlTestPlanEntry
        test_warnings: tuple[PlanWarning, ...]
        test_entry, test_warnings = plan_test(
            test=sql_test,
            project=project,
            sqlglot_enabled=sqlglot_enabled,
        )
        test_entries.append(test_entry)
        all_warnings.extend(test_warnings)

    selected_test_keys: frozenset[CompiledObjectKey] = frozenset(
        entry.key for entry in test_entries
    )
    scoped_keys: frozenset[CompiledObjectKey] = selected_keys | selected_test_keys
    scoped_order: tuple[CompiledObjectKey, ...] = tuple(
        k for k in execution_order if k in scoped_keys
    )

    plan_output: PlanOutput = PlanOutput(
        execution_order=scoped_order,
        model_entries=tuple(model_entries),
        seed_entries=tuple(seed_entries),
        function_entries=tuple(function_entries),
        audit_entries=tuple(audit_entries),
        test_entries=tuple(test_entries),
        selected_keys=selected_keys,
        warnings=tuple(all_warnings),
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        model_targets=model_targets,
        seed_targets=seed_targets,
        function_targets=function_targets,
        source_map=source_map,
    )
    if on_progress is not None:
        on_progress(f"Generated plan. ({time.monotonic() - plan_start:.2f}s)")
    return plan_output


def _build_all_keys(project: CompiledProject) -> dict[str, CompiledObjectKey]:
    keys: dict[str, CompiledObjectKey] = {}
    model: CompiledModel
    for model in project.models:
        keys[model.name] = model.key
    source: CompiledSource
    for source in project.sources:
        keys[source.name] = source.key
    seed: CompiledSeed
    for seed in project.seeds:
        keys[seed.name] = seed.key
    function: CompiledFunction
    for function in project.functions:
        keys[function.name] = function.key
    return keys


def _find_model(project: CompiledProject, name: str) -> CompiledModel | None:
    model: CompiledModel
    for model in project.models:
        if model.name == name:
            return model
    return None
