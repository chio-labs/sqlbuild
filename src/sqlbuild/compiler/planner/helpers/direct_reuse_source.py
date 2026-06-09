"""Direct target reuse source-state helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.constants import PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationDestination,
)
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import FingerprintSet
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    DirectReuseSourceModelSnapshot,
    DirectReuseSourceSnapshot,
    PlannerScope,
)
from sqlbuild.shared.helpers.project_var_values import render_project_var_text
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from sqlbuild.spec.models.targets import resolve_target_config


def build_direct_reuse_source_snapshot(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
) -> DirectReuseSourceSnapshot | None:
    """Read source-target fingerprints and model relation existence for direct reuse."""

    if project.effective_target_name is None or project_config is None or local_config is None:
        return None
    active_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=project.effective_target_name,
    )
    source_target_name: str | None = active_target.reuse_from
    if source_target_name is None:
        return None
    source_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=source_target_name,
    )
    source_vars: dict[str, object] = _build_source_target_vars(
        project_config=project_config,
        local_config=local_config,
        target_config=source_target,
    )
    source_schema: str | None = _resolve_target_value(
        target_value=source_target.schema,
        logical_database=project.effective_target_database,
        logical_schema=project.effective_target_schema,
        default_value=project.effective_target_schema,
        effective_vars=source_vars,
    )
    if source_schema is None:
        raise PlannerInputError(
            f"target '{project.effective_target_name}' has reuse_from = "
            f"'{source_target_name}', but source target '{source_target_name}' does not "
            "resolve to a fingerprint schema"
        )
    source_database: str | None = _resolve_target_value(
        target_value=source_target.database,
        logical_database=project.effective_target_database,
        logical_schema=project.effective_target_schema,
        default_value=project.effective_target_database,
        effective_vars=source_vars,
    )
    try:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            database=source_database,
            schema=source_schema,
            render_qualified_name=adapter.render_qualified_name,
            require_table=True,
        )
    except FingerprintInputError as error:
        raise PlannerInputError(
            f"target '{project.effective_target_name}' has reuse_from = "
            f"'{source_target_name}', but SQLBuild cannot read fingerprint state for "
            f"source target '{source_target_name}'. Reuse requires access to the source "
            "target fingerprint table so SQLBuild can prove the source relation matches "
            "the expected version."
        ) from error

    model_snapshots: dict[str, DirectReuseSourceModelSnapshot] = {}
    model: CompiledModel
    for model in project.models:
        if model.key not in scope.selected_keys:
            continue
        destination: CompiledRelationDestination = _source_model_destination(
            model=model,
            adapter=adapter,
            source_target=source_target,
            source_vars=source_vars,
        )
        model_snapshots[model.name] = DirectReuseSourceModelSnapshot(
            model_name=model.name,
            destination=destination,
            relation_exists=adapter.relation_exists(
                connection,
                database=destination.database,
                schema=destination.schema,
                name=destination.name,
            ),
            built_version_hash=(
                fingerprint_set.fingerprints[model.name].version_hash
                if model.name in fingerprint_set.fingerprints
                else None
            ),
        )
    return DirectReuseSourceSnapshot(
        target_name=source_target_name,
        fingerprint_database=source_database,
        fingerprint_schema=source_schema,
        model_snapshots=model_snapshots,
    )


def _source_model_destination(
    *,
    model: CompiledModel,
    adapter: BaseAdapter,
    source_target: TargetConfig,
    source_vars: dict[str, object],
) -> CompiledRelationDestination:
    database: str | None = _resolve_target_value(
        target_value=source_target.database,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
        default_value=model.destination.logical_database,
        effective_vars=source_vars,
    )
    schema: str | None = _resolve_target_value(
        target_value=source_target.schema,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
        default_value=model.destination.logical_schema,
        effective_vars=source_vars,
    )
    qualified_name: str | None = adapter.render_qualified_name(
        database=database,
        schema=schema,
        name=model.destination.name,
    )
    return CompiledRelationDestination(
        database=database,
        schema=schema,
        name=model.destination.name,
        qualified_name=qualified_name,
        logical_database=model.destination.logical_database,
        logical_schema=model.destination.logical_schema,
    )


def _build_source_target_vars(
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
