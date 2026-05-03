"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompiledSqlTest,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.audit_entry import plan_audit
from sqlbuild.compiler.planner.helpers.buildability import check_buildability
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_tag_index,
    gather_source_columns,
    plan_model,
)
from sqlbuild.compiler.planner.helpers.resolve.helpers.refs import (
    build_model_targets,
    build_seed_targets,
)
from sqlbuild.compiler.planner.helpers.selectors import resolve_selectors
from sqlbuild.compiler.planner.helpers.sql_test_assembly import plan_test
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import (
    gather_warehouse_snapshot,
)
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    MissingUpstream,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SeedPlanEntry,
    SqlTestPlanEntry,
    WarehouseSnapshot,
)
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
    on_progress: Callable[[str], None] | None = None,
) -> PlanOutput:
    """Build a complete execution plan from compiled project and warehouse state."""

    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = _build_all_keys(project)
    tag_index: dict[str, frozenset[CompiledObjectKey]] = build_tag_index(project)

    selected_keys: frozenset[CompiledObjectKey] = resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=tag_index,
    )

    execution_order: tuple[CompiledObjectKey, ...] = topologically_order_keys(upstream_deps)

    execute: Any = adapter.execute
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
    )

    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=selected_keys,
        upstream_deps=upstream_deps,
        snapshot=snapshot,
    )
    if missing:
        names: str = ", ".join(m.key.name for m in missing[:5])
        raise ValueError(
            f"Cannot build selected scope: {len(missing)} missing upstream dependencies ({names})"
        )

    model_targets: dict[str, CompiledRelationTarget] = build_model_targets(project.models)
    seed_targets: dict[str, CompiledRelationTarget] = build_seed_targets(project.seeds)
    source_map: dict[str, SourceEntry] = {
        s.source_entry.name: s.source_entry for s in project.sources
    }
    star_exclude_keyword: str = adapter.star_exclude_keyword()
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = gather_source_columns(
        project=project, adapter=adapter, connection=connection
    )

    sqlglot_enabled: bool = _is_settings_flag(project, "sqlglot", default=False)
    query_change_tracking: bool = _is_settings_flag(project, "query_change_tracking", default=True)

    model_entries: list[ModelPlanEntry] = []
    all_warnings: list[PlanWarning] = []

    key: CompiledObjectKey
    for key in execution_order:
        if key not in selected_keys:
            continue
        if key.resource_type != CompiledResourceType.MODEL:
            continue

        model: CompiledModel | None = _find_model(project, key.name)
        if model is None:
            continue

        entry: ModelPlanEntry
        warnings: tuple[PlanWarning, ...]
        entry, warnings = plan_model(
            model=model,
            snapshot=snapshot,
            model_targets=model_targets,
            seed_targets=seed_targets,
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            star_exclude_keyword=star_exclude_keyword,
            sqlglot_enabled=sqlglot_enabled,
            query_change_tracking=query_change_tracking,
            full_refresh=full_refresh,
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
        )
        model_entries.append(entry)
        all_warnings.extend(warnings)

    seed_entries: list[SeedPlanEntry] = [
        SeedPlanEntry(key=seed.key, name=seed.name, target=seed.target)
        for seed in project.seeds
        if seed.key in selected_keys
    ]

    audit_entries: list[AuditPlanEntry] = []
    audit: CompiledAudit
    for audit in project.audits:
        if not _scope_overlaps(audit.scope_deps, selected_keys):
            continue
        audit_entries.append(
            plan_audit(
                audit=audit,
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
            )
        )

    test_entries: list[SqlTestPlanEntry] = []
    sql_test: CompiledSqlTest
    for sql_test in project.sql_tests:
        if not _scope_overlaps(sql_test.scope_deps, selected_keys):
            continue
        test_entry: SqlTestPlanEntry
        test_warnings: tuple[PlanWarning, ...]
        test_entry, test_warnings = plan_test(
            test=sql_test,
            project=project,
        )
        test_entries.append(test_entry)
        all_warnings.extend(test_warnings)

    scoped_order: tuple[CompiledObjectKey, ...] = tuple(
        k for k in execution_order if k in selected_keys
    )

    return PlanOutput(
        execution_order=scoped_order,
        model_entries=tuple(model_entries),
        seed_entries=tuple(seed_entries),
        audit_entries=tuple(audit_entries),
        test_entries=tuple(test_entries),
        selected_keys=selected_keys,
        warnings=tuple(all_warnings),
    )


def _build_all_keys(project: CompiledProject) -> dict[str, CompiledObjectKey]:
    """Build a name-to-key lookup for all project resources."""

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
    return keys


def _find_model(project: CompiledProject, name: str) -> CompiledModel | None:
    """Find a compiled model by name."""

    model: CompiledModel
    for model in project.models:
        if model.name == name:
            return model
    return None


def _scope_overlaps(
    scope_deps: tuple[CompiledObjectKey, ...],
    selected_keys: frozenset[CompiledObjectKey],
) -> bool:
    """Check if any scope dependency is in the selected keys."""

    dep: CompiledObjectKey
    for dep in scope_deps:
        if dep in selected_keys:
            return True
    return False


def _is_settings_flag(project: CompiledProject, key: str, *, default: bool) -> bool:
    """Check a boolean setting from project effective connection."""

    raw: object | None = project.effective_connection.get(key)
    if isinstance(raw, bool):
        return raw
    return default
