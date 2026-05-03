"""Per-model change detection orchestration."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledModel, InferredColumn
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.helpers.policy import (
    pick_more_aggressive,
    resolve_query_change_backfill,
    resolve_schema_change_backfill,
)
from sqlbuild.compiler.planner.helpers.changes.helpers.query import detect_query_change
from sqlbuild.compiler.planner.helpers.changes.helpers.schema import detect_schema_changes
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    SchemaFinding,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from sqlbuild.compiler.shared.helpers.hashing import (
    compute_ast_hash,
    compute_query_hash,
)


def detect_model_changes(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    sqlglot_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
) -> ChangeDetectionResult:
    """Detect changes for one model and resolve backfill policy."""

    model_name: str = model.name

    if full_refresh:
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.NO_CHANGE,
            backfill=BackfillResult(action=BackfillAction.FULL),
        )

    relation_exists: bool = model_name in snapshot.existing_relations
    fingerprint: Fingerprint | None = snapshot.fingerprints.get(model_name)

    if not relation_exists and fingerprint is None:
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.FIRST_RUN,
            backfill=BackfillResult(action=BackfillAction.FULL),
        )

    query_changed: bool = False
    query_backfill: BackfillResult = BackfillResult(action=BackfillAction.WARN_ONLY)
    if query_change_tracking and fingerprint is not None:
        compiled_query_hash: str = compute_query_hash(model.query_sql)
        compiled_ast_hash: str | None = (
            compute_ast_hash(model.query_sql) if sqlglot_enabled else None
        )
        query_changed = detect_query_change(
            compiled_query_hash=compiled_query_hash,
            compiled_ast_hash=compiled_ast_hash,
            fingerprint=fingerprint,
            sqlglot_enabled=sqlglot_enabled,
        )
        if query_changed:
            raw_policy: str | None = _get_config_str(model, "query_change_backfill")
            query_backfill = resolve_query_change_backfill(query_change_backfill=raw_policy)

    schema_findings: tuple[SchemaFinding, ...] = ()
    schema_backfill: BackfillResult = BackfillResult(action=BackfillAction.WARN_ONLY)
    warehouse_columns: tuple[ColumnInfo, ...] | None = snapshot.existing_columns.get(model_name)
    yml_columns: tuple[ColumnInfo, ...] = _build_yml_columns(model)
    inferred_columns: tuple[InferredColumn, ...] | None = model.inferred_columns
    has_expected: bool = bool(yml_columns) or (
        inferred_columns is not None and bool(inferred_columns)
    )
    type_enforcement: bool = _get_type_enforcement(model)
    if warehouse_columns is not None and has_expected:
        schema_findings = detect_schema_changes(
            yml_columns=yml_columns,
            inferred_columns=inferred_columns,
            warehouse_columns=warehouse_columns,
            type_enforcement=type_enforcement,
        )
        if schema_findings:
            raw_schema_policy: dict[str, str] = _get_config_dict(model, "schema_change_backfill")
            schema_backfill = resolve_schema_change_backfill(
                schema_change_backfill=raw_schema_policy,
                findings=schema_findings,
            )

    backfill: BackfillResult = pick_more_aggressive(query_backfill, schema_backfill)

    change_kind: ChangeKind
    if query_changed:
        change_kind = ChangeKind.QUERY_CHANGED
    elif schema_findings:
        change_kind = ChangeKind.SCHEMA_CHANGED
    else:
        change_kind = ChangeKind.NO_CHANGE

    return ChangeDetectionResult(
        model_name=model_name,
        change_kind=change_kind,
        query_changed=query_changed,
        schema_findings=schema_findings,
        backfill=backfill,
    )


def _get_type_enforcement(model: CompiledModel) -> bool:
    """Resolve whether type enforcement is active for a model."""

    if model.schema_entry is not None and model.schema_entry.type_enforcement is not None:
        return model.schema_entry.type_enforcement
    return False


def _build_yml_columns(model: CompiledModel) -> tuple[ColumnInfo, ...]:
    """Build expected columns from schema.yml declarations."""

    if model.schema_entry is None:
        return ()
    return tuple(
        ColumnInfo(name=col.name, type=col.type)
        for col in model.schema_entry.columns
        if col.type is not None
    )


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None


def _get_config_dict(model: CompiledModel, key: str) -> dict[str, str]:
    """Extract a dict config value from model config."""

    raw: object | None = model.config.values.get(key)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
