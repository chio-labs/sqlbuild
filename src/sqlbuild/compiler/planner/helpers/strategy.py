"""Per-model plan action resolution, schema action resolution, and logical DDL generation."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledRelationTarget,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlanWarning,
    SchemaAction,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    IncrementalStrategy,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    WarningSeverity,
)

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_DDL_MERGE_SOURCE_ALIAS: str = "__source"
_DDL_MERGE_TARGET_ALIAS: str = "target"


def resolve_model_plan_action(
    *,
    model: CompiledModel,
    change_result: ChangeDetectionResult,
    full_refresh: bool,
) -> tuple[PlanAction, PlanReason]:
    """Determine the plan action and reason for a single model."""

    if _is_disabled(model):
        return PlanAction.SKIP, PlanReason.DISABLED

    materialization: MaterializationType = get_materialization_type(model)

    if materialization == MaterializationType.CUSTOM:
        return PlanAction.CUSTOM, _custom_reason(change_result, full_refresh)

    if materialization == MaterializationType.VIEW:
        return PlanAction.CREATE_VIEW, _view_reason(change_result, full_refresh)

    if materialization == MaterializationType.SNAPSHOT:
        return PlanAction.SNAPSHOT, _snapshot_reason(change_result, full_refresh)

    if full_refresh:
        return PlanAction.CREATE_TABLE, PlanReason.FULL_REFRESH

    if change_result.change_kind == ChangeKind.FIRST_RUN:
        return PlanAction.CREATE_TABLE, PlanReason.FIRST_RUN

    if change_result.backfill.action == BackfillAction.FULL:
        reason: PlanReason = _backfill_reason(change_result)
        return PlanAction.CREATE_TABLE, reason

    if materialization == MaterializationType.TABLE:
        return _table_action(change_result)

    return _incremental_action(model, change_result)


def resolve_schema_actions(
    *,
    schema_findings: tuple[SchemaFinding, ...],
    on_schema_change: OnSchemaChange | None,
) -> tuple[SchemaAction, ...]:
    """Resolve concrete schema change actions from findings and on_schema_change config."""

    effective: OnSchemaChange = on_schema_change or _DEFAULT_ON_SCHEMA_CHANGE

    if effective == OnSchemaChange.IGNORE or effective == OnSchemaChange.FAIL:
        return ()

    actions: list[SchemaAction] = []
    finding: SchemaFinding
    for finding in schema_findings:
        if effective == OnSchemaChange.APPEND_NEW_COLUMNS:
            if finding.kind == SchemaChangeKind.COLUMN_ADDED:
                actions.append(
                    SchemaAction(
                        kind=SchemaActionKind.ADD_COLUMN,
                        column_name=finding.column_name,
                        column_type=finding.expected_type,
                    )
                )
        elif effective == OnSchemaChange.SYNC_ALL_COLUMNS:
            if finding.kind == SchemaChangeKind.COLUMN_ADDED:
                actions.append(
                    SchemaAction(
                        kind=SchemaActionKind.ADD_COLUMN,
                        column_name=finding.column_name,
                        column_type=finding.expected_type,
                    )
                )
            elif finding.kind == SchemaChangeKind.COLUMN_REMOVED:
                actions.append(
                    SchemaAction(
                        kind=SchemaActionKind.DROP_COLUMN,
                        column_name=finding.column_name,
                    )
                )
            elif finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
                actions.append(
                    SchemaAction(
                        kind=SchemaActionKind.ALTER_COLUMN_TYPE,
                        column_name=finding.column_name,
                        column_type=finding.expected_type,
                    )
                )

    return tuple(actions)


def build_logical_ddl(
    *,
    action: PlanAction,
    resolved_sql: str,
    target: CompiledRelationTarget,
    unique_key: tuple[str, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
) -> str:
    """Generate the logical DDL string for a model plan entry."""

    qualified_name: str = target.qualified_name or target.name

    if action == PlanAction.CREATE_VIEW:
        return f"CREATE OR REPLACE VIEW {qualified_name} AS (\n{resolved_sql}\n)"

    if action == PlanAction.CREATE_TABLE:
        return f"CREATE TABLE {qualified_name} AS (\n{resolved_sql}\n)"

    if action == PlanAction.INCREMENTAL_APPEND:
        return f"INSERT INTO {qualified_name}\n{resolved_sql}"

    if action == PlanAction.INCREMENTAL_DELETE_INSERT:
        return _build_delete_insert_ddl(
            qualified_name=qualified_name,
            resolved_sql=resolved_sql,
            unique_key=unique_key,
        )

    if action == PlanAction.INCREMENTAL_MERGE:
        return _build_merge_ddl(
            qualified_name=qualified_name,
            resolved_sql=resolved_sql,
            unique_key=unique_key,
            warehouse_columns=warehouse_columns,
        )

    return ""


def build_model_warnings(
    *,
    model_name: str,
    materialization_type: MaterializationType,
    change_result: ChangeDetectionResult,
    schema_actions: tuple[SchemaAction, ...],
    on_schema_change: OnSchemaChange | None,
    type_enforcement: bool,
) -> tuple[PlanWarning, ...]:
    """Build warnings for a single model based on change detection and plan decisions."""

    effective: OnSchemaChange = on_schema_change or _DEFAULT_ON_SCHEMA_CHANGE
    warnings: list[PlanWarning] = []

    if effective == OnSchemaChange.FAIL and change_result.schema_findings:
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message="schema change detected and on_schema_change is set to fail",
            )
        )

    finding: SchemaFinding
    for finding in change_result.schema_findings:
        if type_enforcement and finding.source == SchemaColumnSource.YML:
            if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
                warnings.append(
                    PlanWarning(
                        model_name=model_name,
                        severity=WarningSeverity.WARNING,
                        message=(
                            f"enforced column {finding.column_name} type mismatch: "
                            f"expected {finding.expected_type}, "
                            f"warehouse has {finding.actual_type}"
                        ),
                    )
                )
        elif finding.source == SchemaColumnSource.SQLGLOT:
            if finding.kind in (
                SchemaChangeKind.COLUMN_ADDED,
                SchemaChangeKind.COLUMN_TYPE_CHANGED,
            ):
                warnings.append(
                    PlanWarning(
                        model_name=model_name,
                        severity=WarningSeverity.INFO,
                        message=(
                            f"inferred column {finding.column_name}: {_describe_finding(finding)}"
                        ),
                    )
                )

    if (
        materialization_type == MaterializationType.INCREMENTAL
        and change_result.query_changed
        and change_result.backfill.action == BackfillAction.WARN_ONLY
    ):
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.WARNING,
                message=(
                    f"query changed for '{model_name}'; incremental history will not be "
                    "rebuilt unless you set query_change_backfill. Use "
                    "query_change_backfill full or bounded-<duration> to rebuild history, "
                    "or set settings.query_change_tracking = false in sqlbuild_project.toml "
                    "to disable query-change warnings."
                ),
            )
        )

    has_schema_backfill_findings: bool = any(
        f.kind in (SchemaChangeKind.COLUMN_ADDED, SchemaChangeKind.COLUMN_TYPE_CHANGED)
        for f in change_result.schema_findings
    )
    if has_schema_backfill_findings and not schema_actions:
        if effective == OnSchemaChange.IGNORE:
            warnings.append(
                PlanWarning(
                    model_name=model_name,
                    severity=WarningSeverity.INFO,
                    message="schema change detected but on_schema_change is set to ignore",
                )
            )

    return tuple(warnings)


def _is_disabled(model: CompiledModel) -> bool:
    """Check whether a model is explicitly disabled."""

    raw: object | None = model.config.values.get("enabled")
    if isinstance(raw, bool):
        return not raw
    return False


def _custom_reason(change_result: ChangeDetectionResult, full_refresh: bool) -> PlanReason:
    """Determine the reason for a custom materialization action."""

    if full_refresh:
        return PlanReason.FULL_REFRESH
    if change_result.change_kind == ChangeKind.FIRST_RUN:
        return PlanReason.FIRST_RUN
    if change_result.change_kind == ChangeKind.QUERY_CHANGED:
        return PlanReason.QUERY_CHANGED
    if change_result.change_kind == ChangeKind.SCHEMA_CHANGED:
        return PlanReason.SCHEMA_CHANGED
    return PlanReason.NO_CHANGE


def _view_reason(change_result: ChangeDetectionResult, full_refresh: bool) -> PlanReason:
    """Determine the reason for a view action."""

    if full_refresh:
        return PlanReason.FULL_REFRESH
    if change_result.change_kind == ChangeKind.FIRST_RUN:
        return PlanReason.FIRST_RUN
    if change_result.change_kind == ChangeKind.QUERY_CHANGED:
        return PlanReason.QUERY_CHANGED
    if change_result.change_kind == ChangeKind.SCHEMA_CHANGED:
        return PlanReason.SCHEMA_CHANGED
    return PlanReason.NO_CHANGE


def _snapshot_reason(change_result: ChangeDetectionResult, full_refresh: bool) -> PlanReason:
    """Determine the reason for a snapshot materialization action."""

    if full_refresh:
        return PlanReason.FULL_REFRESH
    if change_result.change_kind == ChangeKind.FIRST_RUN:
        return PlanReason.FIRST_RUN
    if change_result.change_kind == ChangeKind.QUERY_CHANGED:
        return PlanReason.QUERY_CHANGED
    if change_result.change_kind == ChangeKind.SCHEMA_CHANGED:
        return PlanReason.SCHEMA_CHANGED
    return PlanReason.NORMAL_INCREMENTAL


def _backfill_reason(change_result: ChangeDetectionResult) -> PlanReason:
    """Determine the reason when backfill forces a full rebuild."""

    if change_result.query_changed:
        return PlanReason.QUERY_CHANGED
    if change_result.schema_findings:
        return PlanReason.SCHEMA_CHANGED
    return PlanReason.FULL_REFRESH


def _table_action(
    change_result: ChangeDetectionResult,
) -> tuple[PlanAction, PlanReason]:
    """Determine action for a table materialization (non-incremental)."""

    if change_result.change_kind == ChangeKind.QUERY_CHANGED:
        return PlanAction.CREATE_TABLE, PlanReason.QUERY_CHANGED
    if change_result.change_kind == ChangeKind.SCHEMA_CHANGED:
        return PlanAction.CREATE_TABLE, PlanReason.SCHEMA_CHANGED
    return PlanAction.CREATE_TABLE, PlanReason.NO_CHANGE


def _incremental_action(
    model: CompiledModel,
    change_result: ChangeDetectionResult,
) -> tuple[PlanAction, PlanReason]:
    """Determine action for an incremental materialization."""

    raw_strategy: object | None = model.config.values.get("incremental_strategy")
    if not isinstance(raw_strategy, str):
        raise PlannerInputError(
            f"incremental model '{model.name}' is missing required incremental_strategy",
            code="S201",
        )

    reason: PlanReason
    if change_result.change_kind == ChangeKind.QUERY_CHANGED:
        reason = PlanReason.QUERY_CHANGED
    elif change_result.change_kind == ChangeKind.SCHEMA_CHANGED:
        reason = PlanReason.SCHEMA_CHANGED
    else:
        reason = PlanReason.NORMAL_INCREMENTAL

    action_map: dict[str, PlanAction] = {
        IncrementalStrategy.APPEND: PlanAction.INCREMENTAL_APPEND,
        IncrementalStrategy.DELETE_INSERT: PlanAction.INCREMENTAL_DELETE_INSERT,
        IncrementalStrategy.MERGE: PlanAction.INCREMENTAL_MERGE,
    }
    action: PlanAction | None = action_map.get(raw_strategy)
    if action is None:
        raise PlannerInputError(
            f"incremental model '{model.name}' has unknown strategy '{raw_strategy}'",
            code="S202",
        )

    return action, reason


def _build_delete_insert_ddl(
    *,
    qualified_name: str,
    resolved_sql: str,
    unique_key: tuple[str, ...],
) -> str:
    """Build logical DDL for delete+insert strategy."""

    key_list: str = ", ".join(unique_key)
    source_key_list: str = ", ".join(unique_key)
    delete_stmt: str = (
        f"DELETE FROM {qualified_name}\n"
        f"WHERE ({key_list}) IN (SELECT {source_key_list} FROM (\n{resolved_sql}\n))"
    )
    insert_stmt: str = f"INSERT INTO {qualified_name}\n{resolved_sql}"
    return f"{delete_stmt};\n\n{insert_stmt}"


def _build_merge_ddl(
    *,
    qualified_name: str,
    resolved_sql: str,
    unique_key: tuple[str, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
) -> str:
    """Build logical DDL for merge/upsert strategy."""

    on_clause: str = " AND ".join(
        f"{_DDL_MERGE_TARGET_ALIAS}.{k} = {_DDL_MERGE_SOURCE_ALIAS}.{k}" for k in unique_key
    )

    key_set: frozenset[str] = frozenset(unique_key)
    non_key_columns: list[str] = [col.name for col in warehouse_columns if col.name not in key_set]
    all_columns: list[str] = [col.name for col in warehouse_columns]

    update_clause: str = ", ".join(
        f"{col} = {_DDL_MERGE_SOURCE_ALIAS}.{col}" for col in non_key_columns
    )
    insert_columns: str = ", ".join(all_columns)
    insert_values: str = ", ".join(f"{_DDL_MERGE_SOURCE_ALIAS}.{col}" for col in all_columns)

    return (
        f"MERGE INTO {qualified_name} AS {_DDL_MERGE_TARGET_ALIAS}\n"
        f"USING (\n{resolved_sql}\n) AS {_DDL_MERGE_SOURCE_ALIAS}\n"
        f"ON {on_clause}\n"
        f"WHEN MATCHED THEN UPDATE SET {update_clause}\n"
        f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
    )


def _describe_finding(finding: SchemaFinding) -> str:
    """Build a human-readable description for one schema finding."""

    if finding.kind == SchemaChangeKind.COLUMN_ADDED:
        type_suffix: str = f" ({finding.expected_type})" if finding.expected_type else ""
        return f"new column not in warehouse{type_suffix}"
    if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
        return f"expected {finding.expected_type}, warehouse has {finding.actual_type}"
    return f"{finding.kind.value}"


def get_materialization_type(model: CompiledModel) -> MaterializationType:
    """Extract materialization type from model config."""

    raw: object | None = model.config.values.get("materialized")
    if isinstance(raw, str):
        try:
            return MaterializationType(raw)
        except ValueError:
            return MaterializationType.CUSTOM
    return MaterializationType.TABLE
