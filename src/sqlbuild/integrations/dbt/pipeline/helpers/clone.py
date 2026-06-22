"""dbt-only clone execution helpers."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.integrations.dbt.constants import (
    DBT_MANIFEST_CONFIG_KEY,
    DBT_MANIFEST_MATERIALIZED_KEY,
    DBT_MATERIALIZATION_EPHEMERAL,
    DBT_MATERIALIZATION_VIEW,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import DbtCloneOptions, DbtLsNode
from sqlbuild.integrations.dbt.types import DbtSupportedResourceType


def parse_dbt_clone_options(args: tuple[str, ...]) -> DbtCloneOptions:
    """Parse `sqb dbt clone` args into dbt and SQLBuild clone options."""

    dbt_args: list[str] = []
    select: list[str] = []
    exclude: list[str] = []
    hard_copy: bool = False
    no_sql_validation: bool = False
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token in {"--select", "-s"}:
            values: tuple[str, ...]
            values, index = _consume_multi_value(args=args, index=index)
            select.extend(values)
            dbt_args.extend((token, *values))
            continue
        if token == "--exclude":
            values, index = _consume_multi_value(args=args, index=index)
            exclude.extend(values)
            dbt_args.extend((token, *values))
            continue
        if token == "--hard-copy":
            hard_copy = True
            index += 1
            continue
        if token == "--no-sql-validation":
            no_sql_validation = True
            index += 1
            continue
        if token in _dbt_value_flags():
            value: str
            value, index = _consume_one_value(args=args, index=index)
            dbt_args.extend((token, value))
            continue
        dbt_args.append(token)
        index += 1
    return DbtCloneOptions(
        dbt_args=tuple(dbt_args),
        select=tuple(select),
        exclude=tuple(exclude),
        hard_copy=hard_copy,
        no_sql_validation=no_sql_validation,
    )


def execute_dbt_clone(
    *,
    adapter: BaseAdapter,
    connection: Any,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    selected_nodes: tuple[DbtLsNode, ...],
    hard_copy: bool,
) -> CloneExecutionResult:
    """Clone selected dbt models from reuse manifest relations into current relations."""

    results: list[CloneItemResult] = []
    node: DbtLsNode
    for node in selected_nodes:
        if node.resource_type != DbtSupportedResourceType.MODEL:
            continue
        current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(
            node.unique_id
        )
        if current_model is None:
            continue
        if _model_materialization(model=current_model) == DBT_MATERIALIZATION_EPHEMERAL:
            continue
        reuse_model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(
            node.unique_id
        )
        if reuse_model is None:
            continue
        if _model_materialization(model=current_model) == DBT_MATERIALIZATION_VIEW:
            results.append(
                _recreate_dbt_view(
                    adapter=adapter,
                    connection=connection,
                    current_model=current_model,
                    reuse_model=reuse_model,
                )
            )
            continue
        results.append(
            _clone_dbt_relation(
                adapter=adapter,
                connection=connection,
                current_model=current_model,
                reuse_model=reuse_model,
                hard_copy=hard_copy,
            )
        )
    return CloneExecutionResult(item_results=tuple(results))


def _clone_dbt_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    current_model: DbtManifestModel,
    reuse_model: DbtManifestModel,
    hard_copy: bool,
) -> CloneItemResult:
    if not _relation_exists(adapter=adapter, connection=connection, model=reuse_model):
        return _missing_source_result(name=current_model.name)
    recorder: StatementRecorder = StatementRecorder()
    try:
        adapter.drop(
            connection,
            destination=current_model.relation_name,
            if_exists=True,
            statement_recorder=recorder,
        )
        adapter.clone(
            connection,
            origin=reuse_model.relation_name,
            destination=current_model.relation_name,
            hard_copy=hard_copy,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=current_model.name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            executed_statements=recorder.snapshot(),
        )
    action: CloneAction = (
        CloneAction.COPIED
        if hard_copy or not adapter.supports_zero_copy_clone()
        else CloneAction.CLONED
    )
    return CloneItemResult(
        name=current_model.name,
        action=action,
        status=CloneStatus.SUCCESS,
        executed_statements=recorder.snapshot(),
    )


def _recreate_dbt_view(
    *,
    adapter: BaseAdapter,
    connection: Any,
    current_model: DbtManifestModel,
    reuse_model: DbtManifestModel,
) -> CloneItemResult:
    if not _relation_exists(adapter=adapter, connection=connection, model=reuse_model):
        return _missing_source_result(name=current_model.name)
    recorder: StatementRecorder = StatementRecorder()
    try:
        adapter.create_view_as(
            connection,
            destination=current_model.relation_name,
            sql=_compiled_model_sql(model=current_model),
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=current_model.name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            executed_statements=recorder.snapshot(),
        )
    return CloneItemResult(
        name=current_model.name,
        action=CloneAction.RECREATED_VIEW,
        status=CloneStatus.SUCCESS,
        executed_statements=recorder.snapshot(),
    )


def _consume_one_value(*, args: tuple[str, ...], index: int) -> tuple[str, int]:
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise DbtInteropArgumentError(f"{args[index]} requires a value", code="C235")
    return args[index + 1], index + 2


def _consume_multi_value(*, args: tuple[str, ...], index: int) -> tuple[tuple[str, ...], int]:
    values: list[str] = []
    next_index: int = index + 1
    while next_index < len(args) and not args[next_index].startswith("--"):
        values.append(args[next_index])
        next_index += 1
    if not values:
        raise DbtInteropArgumentError(f"{args[index]} requires at least one value", code="C235")
    return tuple(values), next_index


def _dbt_value_flags() -> frozenset[str]:
    return frozenset(
        {
            "--project-dir",
            "--profiles-dir",
            "--target",
            "--target-path",
            "--profile",
            "--vars",
            "--state",
            "--defer-state",
            "--favor-state",
            "--indirect-selection",
            "--selector",
            "--threads",
        }
    )


def _model_materialization(*, model: DbtManifestModel) -> str | None:
    config: object | None = model.payload.get(DBT_MANIFEST_CONFIG_KEY)
    if not isinstance(config, dict):
        return None
    materialized: object | None = cast(dict[str, object], config).get(DBT_MANIFEST_MATERIALIZED_KEY)
    if not isinstance(materialized, str) or not materialized.strip():
        return None
    return materialized.strip().lower()


def _compiled_model_sql(*, model: DbtManifestModel) -> str:
    compiled_code: object | None = model.payload.get("compiled_code")
    if isinstance(compiled_code, str) and compiled_code.strip():
        return compiled_code
    compiled_sql: object | None = model.payload.get("compiled_sql")
    if isinstance(compiled_sql, str) and compiled_sql.strip():
        return compiled_sql
    return model.query_sql


def _relation_exists(*, adapter: BaseAdapter, connection: Any, model: DbtManifestModel) -> bool:
    database: str | None = model.database
    schema: str | None = model.schema
    name: str = model.alias or model.name
    if database is None or schema is None:
        database, schema, name = _relation_parts(relation_name=model.relation_name)
    return adapter.relation_exists(connection, database=database, schema=schema, name=name)


def _relation_parts(*, relation_name: str) -> tuple[str | None, str | None, str]:
    parts: list[str] = [_unquote_relation_part(part=part) for part in relation_name.split(".")]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return None, None, parts[0]


def _unquote_relation_part(*, part: str) -> str:
    return part.strip().strip('"').strip("`").removeprefix("[").removesuffix("]")


def _missing_source_result(*, name: str) -> CloneItemResult:
    return CloneItemResult(
        name=name,
        action=CloneAction.WARNING_MISSING_SOURCE,
        status=CloneStatus.WARNING,
        message="missing in origin environment",
    )
