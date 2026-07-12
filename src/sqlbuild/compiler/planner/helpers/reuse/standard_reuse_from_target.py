"""Standard reuse_from target-state helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.models import RelationLookup
from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.main.project_var_values import render_project_var_text
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    StandardReuseFromTargetModelSnapshot,
    StandardReuseFromTargetSnapshot,
)
from sqlbuild.diagnostics.helpers.logging import log_debug_event
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from sqlbuild.spec.models.targets import resolve_target_config

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")


def build_standard_reuse_from_target_snapshot(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
) -> StandardReuseFromTargetSnapshot | None:
    """Read reuse_from target fingerprints and model relation existence for standard reuse."""

    if project.effective_target_name is None or project_config is None or local_config is None:
        return None
    active_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=project.effective_target_name,
    )
    reuse_from_target_name: str | None = active_target.reuse_from
    if reuse_from_target_name is None:
        return None
    reuse_from_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=reuse_from_target_name,
    )
    reuse_from_vars: dict[str, object] = _build_reuse_from_target_vars(
        project_config=project_config,
        local_config=local_config,
        target_config=reuse_from_target,
    )
    fingerprint_sets: dict[tuple[str | None, str], FingerprintSet] = {}
    model_snapshots: dict[str, StandardReuseFromTargetModelSnapshot] = {}
    reuse_origins_by_model: dict[str, CompiledRelationLocation] = {}
    model: CompiledModel
    for model in project.models:
        if model.key not in scope.selected_keys:
            continue
        reuse_origin_location: CompiledRelationLocation = _reuse_origin_destination(
            model=model,
            adapter=adapter,
            reuse_from_target=reuse_from_target,
            reuse_from_vars=reuse_from_vars,
        )
        if reuse_origin_location.schema is None:
            raise PlannerInputError(
                f"target '{project.effective_target_name}' has reuse_from = "
                f"'{reuse_from_target_name}', but model '{model.name}' reuse origin does not "
                "resolve to a fingerprint schema"
            )
        reuse_origins_by_model[model.name] = reuse_origin_location
    reuse_origin_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (location.database, location.schema, location.name)
            for location in reuse_origins_by_model.values()
        ),
    )
    fingerprint_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (location.database, location.schema, FINGERPRINT_TABLE_NAME)
            for location in reuse_origins_by_model.values()
            if location.schema is not None
        ),
    )
    for model in project.models:
        if model.key not in scope.selected_keys:
            continue
        reuse_origin: CompiledRelationLocation = reuse_origins_by_model[model.name]
        if reuse_origin.schema is None:
            raise PlannerInputError(
                f"target '{project.effective_target_name}' has reuse_from = "
                f"'{reuse_from_target_name}', but model '{model.name}' reuse origin does not "
                "resolve to a fingerprint schema"
            )
        reuse_origin_schema: str = reuse_origin.schema
        fingerprint_cache_key: tuple[str | None, str] = (reuse_origin.database, reuse_origin_schema)
        fingerprint_set: FingerprintSet | None = fingerprint_sets.get(fingerprint_cache_key)
        if fingerprint_set is None:
            fingerprint_set = _read_reuse_origin_fingerprints(
                adapter=adapter,
                connection=connection,
                fingerprint_table_lookup=fingerprint_table_lookup,
                active_target_name=project.effective_target_name,
                reuse_from_target_name=reuse_from_target_name,
                database=reuse_origin.database,
                schema=reuse_origin_schema,
            )
            fingerprint_sets[fingerprint_cache_key] = fingerprint_set
        fingerprint: Fingerprint | None = fingerprint_set.fingerprints.get(model.name)
        model_snapshots[model.name] = StandardReuseFromTargetModelSnapshot(
            model_name=model.name,
            reuse_origin=reuse_origin,
            reuse_origin_fingerprint_database=reuse_origin.database,
            reuse_origin_fingerprint_schema=reuse_origin_schema,
            relation_exists=reuse_origin_lookup.exists(
                database=reuse_origin.database,
                schema=reuse_origin_schema,
                name=reuse_origin.name,
            ),
            built_version_hash=fingerprint.version_hash if fingerprint is not None else None,
            reuse_origin_cursor_max=_read_reuse_origin_cursor_max(
                adapter=adapter,
                connection=connection,
                model=model,
                reuse_origin=reuse_origin,
                reuse_origin_lookup=reuse_origin_lookup,
            ),
        )
    return StandardReuseFromTargetSnapshot(
        reuse_from_target_name=reuse_from_target_name,
        model_snapshots=model_snapshots,
        hard_copy=active_target.reuse_hard_copy,
    )


def _read_reuse_origin_fingerprints(
    *,
    adapter: BaseAdapter,
    connection: Any,
    fingerprint_table_lookup: RelationLookup,
    active_target_name: str,
    reuse_from_target_name: str,
    database: str | None,
    schema: str,
) -> FingerprintSet:
    try:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            table_exists=fingerprint_table_lookup.exists(
                database=database, schema=schema, name=FINGERPRINT_TABLE_NAME
            ),
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
            require_table=True,
        )
    except FingerprintInputError as error:
        raise PlannerInputError(
            f"target '{active_target_name}' has reuse_from = '{reuse_from_target_name}', "
            f"but SQLBuild cannot read fingerprint state for reuse origin schema '{schema}'. "
            "Reuse requires access to the reuse origin fingerprint table so SQLBuild can "
            "prove the reuse origin relation matches the expected version."
        ) from error
    return fingerprint_set


def enforce_standard_reuse_from_source_deferral_conflict(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    defer_sources_to: str | None,
    source_deferral_enabled: bool,
) -> None:
    """Reject source deferral when standard reuse is configured."""

    if not source_deferral_enabled:
        return
    if project.effective_target_name is None or project_config is None or local_config is None:
        return
    active_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=project.effective_target_name,
    )
    if active_target.reuse_from is None:
        return
    source_deferral_target: str | None = defer_sources_to or active_target.defer_sources_to
    if source_deferral_target is None:
        return
    raise PlannerInputError(
        f"target '{project.effective_target_name}' has reuse_from = "
        f"'{active_target.reuse_from}', but source deferral is active. Standard target "
        "reuse requires the active target source context so freshness and cursor "
        "comparisons are trustworthy. Remove defer_sources_to or reuse_from."
    )


def _reuse_origin_destination(
    *,
    model: CompiledModel,
    adapter: BaseAdapter,
    reuse_from_target: TargetConfig,
    reuse_from_vars: dict[str, object],
) -> CompiledRelationLocation:
    database: str | None = _resolve_target_value(
        target_value=reuse_from_target.database,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
        default_value=model.destination.logical_database,
        effective_vars=reuse_from_vars,
    )
    schema: str | None = _resolve_target_value(
        target_value=reuse_from_target.schema,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
        default_value=model.destination.logical_schema,
        effective_vars=reuse_from_vars,
    )
    qualified_name: str | None = adapter.render_qualified_name(
        database=database,
        schema=schema,
        name=model.destination.name,
    )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=model.destination.name,
        qualified_name=qualified_name,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
    )


def _read_reuse_origin_cursor_max(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model: CompiledModel,
    reuse_origin: CompiledRelationLocation,
    reuse_origin_lookup: RelationLookup,
) -> str | None:
    cursor_column: str | None = _get_config_str(model=model, key="cursor")
    materialized: str | None = _get_config_str(model=model, key="materialized")
    if (
        cursor_column is None
        or materialized != "incremental"
        or reuse_origin.qualified_name is None
    ):
        return None
    if not reuse_origin_lookup.exists(
        database=reuse_origin.database, schema=reuse_origin.schema, name=reuse_origin.name
    ):
        return None
    rendered_cursor_column: str = adapter.render_identifier(cursor_column)
    sql: str = (
        f"SELECT CAST(MAX({rendered_cursor_column}) AS VARCHAR) FROM {reuse_origin.qualified_name}"
    )
    try:
        result: Any = adapter.execute(connection=connection, sql=sql)
    except Exception as exc:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message=(
                "reuse_from cursor high-water read failed; "
                "treating reuse origin cursor as unavailable"
            ),
            sqlbuild_model_name=model.name,
            sqlbuild_reuse_origin=reuse_origin.qualified_name,
            sqlbuild_error=str(exc),
        )
        return None
    row: Any = result.fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _get_config_str(*, model: CompiledModel, key: str) -> str | None:
    value: object | None = model.config.values.get(key)
    return value if isinstance(value, str) else None


def _build_reuse_from_target_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig,
) -> dict[str, object]:
    values: dict[str, object] = dict(project_config.vars)
    values.update(target_config.vars)
    values.update(local_config.vars)
    return values


def _resolve_target_value(
    *,
    target_value: str | None,
    logical_database: str | None,
    logical_schema: str | None,
    default_value: str | None,
    effective_vars: dict[str, object],
) -> str | None:
    if target_value is None or target_value == PRESERVE_TARGET_VALUE:
        return default_value

    unsupported_ctx_keys: tuple[str, ...] = ("${CTX:database}", "${CTX:schema}")
    unsupported_ctx_key: str
    for unsupported_ctx_key in unsupported_ctx_keys:
        if unsupported_ctx_key in target_value:
            raise PlannerInputError(
                f"reuse_from target value uses unsupported context key "
                f"'{unsupported_ctx_key}'. Use '${{CTX:model.database}}' or "
                "'${CTX:model.schema}' instead."
            )

    result: str = target_value.replace("${CTX:model.database}", logical_database or "")
    result = result.replace("${CTX:model.schema}", logical_schema or "")
    variable_name: str
    variable_value: object
    for variable_name, variable_value in effective_vars.items():
        result = result.replace(
            f"${{{variable_name}}}",
            render_project_var_text(
                value=variable_value,
                label=f"target variable '${{{variable_name}}}'",
            ),
        )
    return result
