"""Per-model change detection orchestration."""

from __future__ import annotations

import logging

from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.config import get_config_str
from sqlbuild.compiler.planner.helpers.changes.metadata import version_identity_metadata_payload
from sqlbuild.compiler.planner.helpers.changes.policy import (
    pick_more_aggressive,
    resolve_replay_on_change,
)
from sqlbuild.compiler.planner.helpers.changes.query import detect_query_change
from sqlbuild.compiler.planner.helpers.changes.schema import detect_schema_changes
from sqlbuild.compiler.planner.helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner.main.planning.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.planning.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerScope,
    SchemaFinding,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason
from sqlbuild.diagnostics.helpers.logging import log_debug_event, log_sql
from sqlbuild.shared.helpers.identity.hashing import compute_query_hash


def detect_changes(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    full_refresh: bool,
    expected_version_hashes: dict[str, str] | None = None,
    expected_metadata_jsons: dict[str, str] | None = None,
) -> PlannerChangeResults:
    """Detect selected model and function changes."""

    model_changes: dict[str, ChangeDetectionResult] = {}
    function_local_hashes: dict[str, str] = build_function_local_hashes(
        functions=project.functions,
    )
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key not in scope.selected_keys or key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        if model is None:
            continue
        model_changes[model.name] = detect_model_changes(
            model=model,
            snapshot=snapshot,
            sql_analysis_enabled=project.settings.sql_analysis,
            query_change_tracking=project.settings.query_change_tracking,
            full_refresh=full_refresh,
            function_local_hashes=function_local_hashes,
            expected_version_hash=(expected_version_hashes or {}).get(model.name),
            expected_metadata_json=(expected_metadata_jsons or {}).get(model.name),
        )

    function_changes: dict[str, FunctionChangeResult] = {}
    function: CompiledFunction
    for function in project.functions:
        fingerprint_sql: str = build_compiled_function_fingerprint_sql(function)
        if function.key not in scope.selected_keys:
            function_changes[function.name] = FunctionChangeResult(
                fingerprint_sql=fingerprint_sql,
            )
            continue
        function_reason: PlanReason
        function_backfill: BackfillResult
        function_reason, function_backfill = detect_function_change(
            function=function,
            fingerprint_sql=fingerprint_sql,
            snapshot=snapshot,
            query_change_tracking=project.settings.query_change_tracking,
            full_refresh=full_refresh,
        )
        function_changes[function.name] = FunctionChangeResult(
            fingerprint_sql=fingerprint_sql,
            reason=function_reason,
            backfill=function_backfill,
        )

    return PlannerChangeResults(models=model_changes, functions=function_changes)


def detect_model_changes(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    function_local_hashes: dict[str, str] | None = None,
    expected_version_hash: str | None = None,
    expected_metadata_json: str | None = None,
) -> ChangeDetectionResult:
    """Detect changes for one model and resolve backfill policy."""

    model_name: str = model.name
    metadata_json: str = expected_metadata_json or build_model_version_identity_metadata_json(
        model=model,
        function_local_hashes=function_local_hashes,
    )

    if full_refresh:
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.NO_CHANGE,
            backfill=BackfillResult(action=BackfillAction.FULL),
            fingerprint_metadata_json=metadata_json,
            fingerprint_version_hash=expected_version_hash,
        )

    relation_exists: bool = model_name in snapshot.existing_relations
    fingerprint: Fingerprint | None = snapshot.fingerprints.models.get(model_name)

    if not relation_exists and fingerprint is None:
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.FIRST_RUN,
            backfill=BackfillResult(action=BackfillAction.FULL),
            fingerprint_metadata_json=metadata_json,
            fingerprint_version_hash=expected_version_hash,
        )

    query_changed: bool = False
    config_changed: bool = (
        fingerprint is not None
        and fingerprint.metadata_json != "{}"
        and version_identity_metadata_payload(metadata_json)
        != version_identity_metadata_payload(fingerprint.metadata_json)
    )
    replay_backfill: BackfillResult = BackfillResult(action=BackfillAction.FORWARD_ONLY)
    if query_change_tracking and fingerprint is not None:
        debug_logger: logging.Logger = logging.getLogger("sqlbuild.planner.changes")
        compiled_query_hash: str = compute_query_hash(model.query_sql)
        query_changed = detect_query_change(
            compiled_query_hash=compiled_query_hash,
            fingerprint=fingerprint,
        )
        log_debug_event(
            logger=debug_logger,
            message=(
                "fingerprint comparison"
                f" compiled_query_hash={compiled_query_hash}"
                f" fingerprint_definition_hash={fingerprint.definition_hash}"
                f" query_changed={query_changed}"
            ),
            sqlbuild_subject="model",
            sqlbuild_name=model_name,
            sqlbuild_event="query_change_check",
            sqlbuild_phase="planner",
            sqlbuild_status="changed" if query_changed else "unchanged",
        )
        log_sql(logger=debug_logger, sql=model.query_sql, action="compiled_query")
        log_sql(logger=debug_logger, sql=fingerprint.definition, action="fingerprint_definition")
        if query_changed:
            raw_policy: str | None = get_config_str(model=model, key="replay_on_change")
            replay_backfill = resolve_replay_on_change(replay_on_change=raw_policy)

    schema_findings: tuple[SchemaFinding, ...] = ()
    schema_backfill: BackfillResult = BackfillResult(action=BackfillAction.FORWARD_ONLY)
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
            raw_policy = get_config_str(model=model, key="replay_on_change")
            schema_backfill = resolve_replay_on_change(replay_on_change=raw_policy)

    backfill: BackfillResult = pick_more_aggressive(a=replay_backfill, b=schema_backfill)

    change_kind: ChangeKind
    if query_changed:
        change_kind = ChangeKind.QUERY_CHANGED
    elif schema_findings:
        change_kind = ChangeKind.SCHEMA_CHANGED
    elif config_changed:
        change_kind = ChangeKind.CONFIG_CHANGED
    else:
        change_kind = ChangeKind.NO_CHANGE

    return ChangeDetectionResult(
        model_name=model_name,
        change_kind=change_kind,
        query_changed=query_changed,
        config_changed=config_changed,
        fingerprint_metadata_json=metadata_json,
        previous_metadata_json=fingerprint.metadata_json if fingerprint is not None else None,
        fingerprint_version_hash=expected_version_hash,
        previous_version_hash=fingerprint.version_hash if fingerprint is not None else None,
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
