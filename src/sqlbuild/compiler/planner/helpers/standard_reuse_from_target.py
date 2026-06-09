"""Standard reuse_from target-state helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import FingerprintSet
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    StandardReuseFromTargetModelSnapshot,
    StandardReuseFromTargetSnapshot,
)
from sqlbuild.shared.helpers.project_var_values import render_project_var_text
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from sqlbuild.spec.models.targets import resolve_target_config


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
    reuse_from_schema: str | None = _resolve_target_value(
        target_value=reuse_from_target.schema,
        logical_database=project.effective_target_database,
        logical_schema=project.effective_target_schema,
        default_value=project.effective_target_schema,
        effective_vars=reuse_from_vars,
    )
    if reuse_from_schema is None:
        raise PlannerInputError(
            f"target '{project.effective_target_name}' has reuse_from = "
            f"'{reuse_from_target_name}', but reuse_from target "
            f"'{reuse_from_target_name}' does not resolve to a fingerprint schema"
        )
    reuse_from_database: str | None = _resolve_target_value(
        target_value=reuse_from_target.database,
        logical_database=project.effective_target_database,
        logical_schema=project.effective_target_schema,
        default_value=project.effective_target_database,
        effective_vars=reuse_from_vars,
    )
    try:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            database=reuse_from_database,
            schema=reuse_from_schema,
            render_qualified_name=adapter.render_qualified_name,
            require_table=True,
        )
    except FingerprintInputError as error:
        raise PlannerInputError(
            f"target '{project.effective_target_name}' has reuse_from = "
            f"'{reuse_from_target_name}', but SQLBuild cannot read fingerprint state for "
            f"reuse_from target '{reuse_from_target_name}'. Reuse requires access to the "
            "reuse_from target fingerprint table so SQLBuild can prove the reuse_from "
            "relation matches the expected version."
        ) from error

    model_snapshots: dict[str, StandardReuseFromTargetModelSnapshot] = {}
    model: CompiledModel
    for model in project.models:
        if model.key not in scope.selected_keys:
            continue
        reuse_origin: CompiledRelationLocation = _reuse_origin_destination(
            model=model,
            adapter=adapter,
            reuse_from_target=reuse_from_target,
            reuse_from_vars=reuse_from_vars,
        )
        model_snapshots[model.name] = StandardReuseFromTargetModelSnapshot(
            model_name=model.name,
            reuse_origin=reuse_origin,
            relation_exists=adapter.relation_exists(
                connection,
                database=reuse_origin.database,
                schema=reuse_origin.schema,
                name=reuse_origin.name,
            ),
            built_version_hash=(
                fingerprint_set.fingerprints[model.name].version_hash
                if model.name in fingerprint_set.fingerprints
                else None
            ),
        )
    return StandardReuseFromTargetSnapshot(
        reuse_from_target_name=reuse_from_target_name,
        fingerprint_database=reuse_from_database,
        fingerprint_schema=reuse_from_schema,
        model_snapshots=model_snapshots,
        hard_copy=active_target.reuse_hard_copy,
    )


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

    result: str = target_value.replace("${CTX:database}", logical_database or "")
    result = result.replace("${CTX:schema}", logical_schema or "")
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
