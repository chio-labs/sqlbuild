"""Per-model change detection orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.changes.metadata import (
    changed_local_function_names,
    non_function_identity_metadata_payload,
    recorded_declared_columns_hash,
    version_identity_metadata_payload,
    with_declared_columns_hash,
    with_origin_cursor_input_names,
)
from sqlbuild.compiler.planner._helpers.changes.policy import (
    pick_more_aggressive,
    resolve_replay_on_change,
)
from sqlbuild.compiler.planner._helpers.changes.query import detect_query_change
from sqlbuild.compiler.planner._helpers.changes.reference_renames import origin_reference_names
from sqlbuild.compiler.planner._helpers.changes.schema import detect_schema_changes
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner._helpers.identity.hashing import model_definition_hash
from sqlbuild.compiler.planner._helpers.identity.model_metadata import declared_columns_hash
from sqlbuild.compiler.planner.constants import EMPTY_FINGERPRINT_METADATA_JSON
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
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
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from sqlbuild.compiler.python_nodes.main.hook_identities import build_hook_identities
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.diagnostics.main.log_sql import log_sql
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


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

    model_changes: dict[str, ChangeDetectionResult] = detect_model_changes_in_scope(
        project=project,
        scope=scope,
        snapshot=snapshot,
        expected_version_hashes=expected_version_hashes,
        expected_metadata_jsons=expected_metadata_jsons,
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
        function_changes[function.name] = FunctionChangeResult(
            fingerprint_sql=fingerprint_sql,
            reason=detect_function_change(
                function=function,
                fingerprint_sql=fingerprint_sql,
                fingerprint=snapshot.fingerprints.functions.get(function.name),
                query_change_tracking=project.settings.query_change_tracking,
                full_refresh=full_refresh,
                dialect=snapshot.column_dialect,
            ),
        )

    return PlannerChangeResults(models=model_changes, functions=function_changes)


def detect_model_changes_in_scope(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    query_change_tracking: bool | None = None,
    expected_version_hashes: dict[str, str] | None = None,
    expected_metadata_jsons: dict[str, str] | None = None,
) -> dict[str, ChangeDetectionResult]:
    """Detect changes for selected models without inspecting functions."""

    model_changes: dict[str, ChangeDetectionResult] = {}
    effective_query_change_tracking: bool = (
        project.settings.query_change_tracking
        if query_change_tracking is None
        else query_change_tracking
    )
    function_local_hashes: dict[str, str] = build_function_local_hashes(
        functions=project.functions, dialect=project.sql_analysis_dialect
    )
    hook_version_hashes: dict[str, str] = {
        name: identity.version_hash
        for name, identity in build_hook_identities(project.hook_functions).items()
    }
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
            query_change_tracking=effective_query_change_tracking,
            full_refresh=False,
            function_local_hashes=function_local_hashes,
            hook_version_hashes=hook_version_hashes,
            expected_version_hash=(expected_version_hashes or {}).get(model.name),
            expected_metadata_json=(expected_metadata_jsons or {}).get(model.name),
        )
    return model_changes


def detect_model_changes(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    function_local_hashes: dict[str, str] | None = None,
    hook_version_hashes: dict[str, str] | None = None,
    expected_version_hash: str | None = None,
    expected_metadata_json: str | None = None,
) -> ChangeDetectionResult:
    """Detect changes for one model and resolve backfill policy."""

    model_name: str = model.name
    current_columns_hash: str = declared_columns_hash(model=model)
    metadata_json: str = with_declared_columns_hash(
        metadata_json=expected_metadata_json
        or build_model_version_identity_metadata_json(
            model=model,
            function_local_hashes=function_local_hashes,
            hook_version_hashes=hook_version_hashes,
        ),
        declared_columns_hash=current_columns_hash,
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
    compiled_query_hash: str | None = (
        model_definition_hash(
            model_name=model_name, query_sql=model.query_sql, dialect=snapshot.column_dialect
        )
        if query_change_tracking and fingerprint is not None
        else None
    )

    if not relation_exists and model_name in snapshot.renamed_models:
        renamed_query_changed: bool = (
            compiled_query_hash is not None
            and fingerprint is not None
            and detect_query_change(
                compiled_query_hash=compiled_query_hash, fingerprint=fingerprint
            )
        )
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.RENAMED,
            query_changed=renamed_query_changed,
            backfill=(
                resolve_replay_on_change(
                    replay_on_change=get_config_str(
                        values=model.config.values, key="replay_on_change"
                    )
                )
                if renamed_query_changed
                else BackfillResult(action=BackfillAction.FORWARD_ONLY)
            ),
            fingerprint_metadata_json=metadata_json,
            previous_metadata_json=fingerprint.metadata_json if fingerprint is not None else None,
            fingerprint_version_hash=expected_version_hash,
            previous_version_hash=fingerprint.version_hash if fingerprint is not None else None,
        )
    if not relation_exists:
        return ChangeDetectionResult(
            model_name=model_name,
            change_kind=ChangeKind.FIRST_RUN,
            backfill=BackfillResult(action=BackfillAction.FULL),
            fingerprint_metadata_json=metadata_json,
            fingerprint_version_hash=expected_version_hash,
            recorded_build_relation_missing=fingerprint is not None,
        )

    query_changed: bool = False
    recorded_metadata_json: str | None = (
        fingerprint.metadata_json
        if fingerprint is not None and fingerprint.metadata_json != EMPTY_FINGERPRINT_METADATA_JSON
        else None
    )
    changed_functions: tuple[str, ...] = (
        changed_local_function_names(
            metadata_json=metadata_json, previous_metadata_json=recorded_metadata_json
        )
        if query_change_tracking and recorded_metadata_json is not None
        else ()
    )
    identity_payload: Callable[[str | None], object] = (
        non_function_identity_metadata_payload
        if changed_functions
        else version_identity_metadata_payload
    )
    origin_names: dict[str, str] | None = (
        origin_reference_names(
            query_sql=model.query_sql,
            recorded=fingerprint,
            renames=snapshot.reference_renames,
            dialect=snapshot.column_dialect,
        )
        if compiled_query_hash is not None
        and fingerprint is not None
        and snapshot.reference_renames
        and compiled_query_hash != fingerprint.definition_hash
        else None
    )
    config_changed: bool = recorded_metadata_json is not None and identity_payload(
        with_origin_cursor_input_names(metadata_json=metadata_json, renamed_refs=origin_names)
        if origin_names is not None
        else metadata_json
    ) != identity_payload(recorded_metadata_json)
    replay_backfill: BackfillResult = BackfillResult(action=BackfillAction.FORWARD_ONLY)
    if compiled_query_hash is not None and fingerprint is not None:
        debug_logger: logging.Logger = logging.getLogger("sqlbuild.planner.changes")
        query_changed = origin_names is None and detect_query_change(
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
    if query_changed or changed_functions:
        replay_backfill = resolve_replay_on_change(
            replay_on_change=get_config_str(values=model.config.values, key="replay_on_change")
        )

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
            inferred_schema_complete=not model.fast_lineage_has_star,
            dynamic_columns=(
                model.schema_entry.dynamic_columns if model.schema_entry is not None else ()
            ),
            dialect=snapshot.column_dialect,
        )
        recorded_columns_hash: str | None = recorded_declared_columns_hash(recorded_metadata_json)
        declared_columns_changed: bool = (
            recorded_columns_hash is not None and recorded_columns_hash != current_columns_hash
        )
        if schema_findings and (
            query_changed or changed_functions or config_changed or declared_columns_changed
        ):
            schema_backfill = resolve_replay_on_change(
                replay_on_change=get_config_str(values=model.config.values, key="replay_on_change")
            )

    backfill: BackfillResult = pick_more_aggressive(a=replay_backfill, b=schema_backfill)

    change_kind: ChangeKind
    if query_changed:
        change_kind = ChangeKind.QUERY_CHANGED
    elif changed_functions:
        change_kind = ChangeKind.FUNCTION_CHANGED
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
        changed_functions=changed_functions,
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
