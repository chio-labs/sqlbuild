"""dbt-only clone execution helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.models import RelationLookup
from sqlbuild.executor.clone.main.clone_relation_operation import clone_relation_by_names
from sqlbuild.executor.clone.main.recreate_view_operation import recreate_view_by_names
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneItemCallback
from sqlbuild.integrations.dbt.constants import (
    DBT_MATERIALIZATION_EPHEMERAL,
    DBT_MATERIALIZATION_VIEW,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.main.manifest.manifest_model_materialization import (
    dbt_manifest_model_materialization,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import DbtCloneOptions, DbtLsNode
from sqlbuild.integrations.dbt.pipeline.constants import (
    DBT_CLONE_POSITIONAL_SELECT_TOKEN,
    DBT_EXCLUDE_FLAG,
    DBT_HARD_COPY_FLAG,
    DBT_NO_SQL_VALIDATION_FLAG,
    DBT_SELECT_FLAGS,
)
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
        if token in DBT_SELECT_FLAGS:
            values: tuple[str, ...]
            values, index = _consume_multi_value(args=args, index=index)
            select.extend(values)
            dbt_args.extend((token, *values))
            continue
        if token == DBT_EXCLUDE_FLAG:
            values, index = _consume_multi_value(args=args, index=index)
            exclude.extend(values)
            dbt_args.extend((token, *values))
            continue
        if token == DBT_HARD_COPY_FLAG:
            hard_copy = True
            index += 1
            continue
        if token == DBT_NO_SQL_VALIDATION_FLAG:
            no_sql_validation = True
            index += 1
            continue
        if token in _dbt_value_flags():
            value: str
            value, index = _consume_one_value(args=args, index=index)
            dbt_args.extend((token, value))
            continue
        if (
            token == DBT_CLONE_POSITIONAL_SELECT_TOKEN
            and index + 1 < len(args)
            and not args[index + 1].startswith("--")
        ):
            selector: str = args[index + 1]
            raise DbtInteropArgumentError(
                "unexpected positional argument 'select'",
                code="C350",
                help=f"Use --select {selector} to choose dbt models for clone.",
            )
        if not token.startswith("--"):
            raise DbtInteropArgumentError(
                f"unexpected positional argument {token!r}",
                code="C350",
                help=f"Use --select {token} to choose dbt models for clone.",
            )
        dbt_args.append(token)
        index += 1
    options: DbtCloneOptions = DbtCloneOptions(
        dbt_args=tuple(dbt_args),
        select=tuple(select),
        exclude=tuple(exclude),
        hard_copy=hard_copy,
        no_sql_validation=no_sql_validation,
    )
    validate_dbt_clone_selection(options=options)
    return options


def validate_dbt_clone_selection(*, options: DbtCloneOptions) -> None:
    """Reject dbt clone requests that would otherwise expand to the whole project."""

    if options.select:
        return
    raise DbtInteropArgumentError(
        "sqb dbt clone requires an explicit --select",
        code="C350",
        help="Refusing to clone the entire dbt project. Use --select to choose dbt models.",
    )


def execute_dbt_clone(
    *,
    adapter: BaseAdapter,
    connection: Any,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    selected_nodes: tuple[DbtLsNode, ...],
    hard_copy: bool,
    on_start: Callable[[int], None] | None = None,
    on_item: CloneItemCallback | None = None,
) -> CloneExecutionResult:
    """Clone selected dbt models from reuse manifest relations into current relations."""

    clonable_models: tuple[tuple[DbtManifestModel, DbtManifestModel], ...] = tuple(
        (current_model, reuse_model)
        for node in selected_nodes
        if node.resource_type == DbtSupportedResourceType.MODEL
        and (current_model := current_manifest.models_by_unique_id.get(node.unique_id)) is not None
        and dbt_manifest_model_materialization(model=current_model) != DBT_MATERIALIZATION_EPHEMERAL
        and (reuse_model := reuse_manifest.models_by_unique_id.get(node.unique_id)) is not None
    )
    clonable_models = _order_clone_models(current_manifest=current_manifest, models=clonable_models)
    total: int = len(clonable_models)
    if on_start is not None:
        on_start(total)
    origin_locations: dict[str, tuple[str | None, str | None, str]] = {
        reuse_model.unique_id: _relation_location(model=reuse_model)
        for _, reuse_model in clonable_models
    }
    origin_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(origin_locations.values()),
    )
    results: list[CloneItemResult] = []
    index: int = 0
    current_model: DbtManifestModel
    reuse_model: DbtManifestModel
    for current_model, reuse_model in clonable_models:
        index += 1
        origin_database, origin_schema, origin_name = origin_locations[reuse_model.unique_id]
        origin_exists: bool = origin_lookup.exists(
            database=origin_database, schema=origin_schema, name=origin_name
        )
        if dbt_manifest_model_materialization(model=current_model) == DBT_MATERIALIZATION_VIEW:
            item_result: CloneItemResult = recreate_view_by_names(
                name=current_model.name,
                origin_relation=reuse_model.relation_name,
                destination_relation=current_model.relation_name,
                view_sql=_compiled_model_sql(model=current_model),
                origin_exists=origin_exists,
                adapter=adapter,
                connection=connection,
            )
        else:
            item_result = clone_relation_by_names(
                name=current_model.name,
                origin_relation=reuse_model.relation_name,
                destination_relation=current_model.relation_name,
                origin_exists=origin_exists,
                adapter=adapter,
                connection=connection,
                hard_copy=hard_copy,
                origin_is_transient=origin_lookup.is_transient(
                    database=origin_database,
                    schema=origin_schema,
                    name=origin_name,
                ),
            )
        results.append(item_result)
        if on_item is not None:
            on_item(index=index, total=total, item=item_result)
    return CloneExecutionResult(item_results=tuple(results))


def _order_clone_models(
    *,
    current_manifest: DbtManifestIndex,
    models: tuple[tuple[DbtManifestModel, DbtManifestModel], ...],
) -> tuple[tuple[DbtManifestModel, DbtManifestModel], ...]:
    selected_by_unique_id: dict[str, tuple[DbtManifestModel, DbtManifestModel]] = {
        current_model.unique_id: (current_model, reuse_model)
        for current_model, reuse_model in models
    }
    ordered: tuple[tuple[DbtManifestModel, DbtManifestModel], ...] = ()
    visited: frozenset[str] = frozenset()
    current_model: DbtManifestModel
    for current_model, _ in models:
        ordered, visited = _visit_clone_model(
            unique_id=current_model.unique_id,
            current_manifest=current_manifest,
            selected_by_unique_id=selected_by_unique_id,
            ordered=ordered,
            visited=visited,
            visiting=frozenset(),
        )
    return ordered


def _visit_clone_model(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    selected_by_unique_id: dict[str, tuple[DbtManifestModel, DbtManifestModel]],
    ordered: tuple[tuple[DbtManifestModel, DbtManifestModel], ...],
    visited: frozenset[str],
    visiting: frozenset[str],
) -> tuple[tuple[tuple[DbtManifestModel, DbtManifestModel], ...], frozenset[str]]:
    if unique_id in visited or unique_id in visiting:
        return ordered, visited
    selected_pair: tuple[DbtManifestModel, DbtManifestModel] | None = selected_by_unique_id.get(
        unique_id
    )
    if selected_pair is None:
        return ordered, visited
    next_visiting: frozenset[str] = visiting | {unique_id}
    dependency_unique_id: str
    for dependency_unique_id in selected_pair[0].depends_on_nodes:
        if dependency_unique_id in current_manifest.models_by_unique_id:
            ordered, visited = _visit_clone_model(
                unique_id=dependency_unique_id,
                current_manifest=current_manifest,
                selected_by_unique_id=selected_by_unique_id,
                ordered=ordered,
                visited=visited,
                visiting=next_visiting,
            )
    return (*ordered, selected_pair), visited | {unique_id}


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


def _compiled_model_sql(*, model: DbtManifestModel) -> str:
    compiled_code: object | None = model.payload.get("compiled_code")
    if isinstance(compiled_code, str) and compiled_code.strip():
        return compiled_code
    compiled_sql: object | None = model.payload.get("compiled_sql")
    if isinstance(compiled_sql, str) and compiled_sql.strip():
        return compiled_sql
    return model.query_sql


def _relation_location(*, model: DbtManifestModel) -> tuple[str | None, str | None, str]:
    database: str | None = model.database
    schema: str | None = model.schema
    name: str = model.alias or model.name
    if database is None or schema is None:
        return _relation_parts(relation_name=model.relation_name)
    return database, schema, name


def _relation_parts(*, relation_name: str) -> tuple[str | None, str | None, str]:
    parts: list[str] = [_unquote_relation_part(part=part) for part in relation_name.split(".")]
    database_schema_relation_part_count: int = 3
    schema_relation_part_count: int = 2
    if len(parts) >= database_schema_relation_part_count:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == schema_relation_part_count:
        return None, parts[0], parts[1]
    return None, None, parts[0]


def _unquote_relation_part(*, part: str) -> str:
    return part.strip().strip('"').strip("`").removeprefix("[").removesuffix("]")
