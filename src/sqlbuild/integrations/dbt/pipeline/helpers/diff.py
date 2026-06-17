"""dbt-only diff execution helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import CursorValue, RowDiffResult, SchemaDiffResult
from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError, DbtInteropConfigError
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import DbtDiffOptions, DbtLsNode


def parse_dbt_diff_options(args: tuple[str, ...]) -> DbtDiffOptions:
    """Parse `sqb dbt diff` args into dbt and SQLBuild diff options."""

    dbt_args: list[str] = []
    select: list[str] = []
    exclude: list[str] = []
    full: bool = False
    schema_only: bool = False
    bounded: str | None = None
    verbose: bool = False
    max_column_examples: int = 3
    max_row_only_examples: int = 3
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
        if token == "--full":
            full = True
            index += 1
            continue
        if token == "--schema-only":
            schema_only = True
            index += 1
            continue
        if token == "--bounded":
            bounded, index = _consume_one_value(args=args, index=index)
            continue
        if token in {"--verbose", "-v"}:
            verbose = True
            max_column_examples = 10
            max_row_only_examples = 10
            index += 1
            continue
        if token == "--max-column-examples":
            raw_value: str
            raw_value, index = _consume_one_value(args=args, index=index)
            max_column_examples = _parse_positive_int(raw_value, flag=token)
            continue
        if token == "--max-row-only-examples":
            raw_value, index = _consume_one_value(args=args, index=index)
            max_row_only_examples = _parse_positive_int(raw_value, flag=token)
            continue
        if token in _dbt_value_flags():
            value: str
            value, index = _consume_one_value(args=args, index=index)
            dbt_args.extend((token, value))
            continue
        if token in _dbt_bool_flags():
            dbt_args.append(token)
            index += 1
            continue
        dbt_args.append(token)
        index += 1
    selected_modes: int = int(full) + int(schema_only) + int(bounded is not None)
    if selected_modes != 1:
        raise DbtInteropArgumentError(
            "dbt diff requires exactly one of --full, --schema-only, or --bounded",
            code="C201",
        )
    return DbtDiffOptions(
        dbt_args=tuple(dbt_args),
        select=tuple(select),
        exclude=tuple(exclude),
        full=full,
        schema_only=schema_only,
        bounded=bounded,
        verbose=verbose,
        max_column_examples=max_column_examples,
        max_row_only_examples=max_row_only_examples,
    )


def execute_dbt_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    selected_nodes: tuple[DbtLsNode, ...],
    options: DbtDiffOptions,
) -> DiffExecutionResult:
    """Execute schema/row diffs for selected dbt models."""

    results: list[ModelDiffResult] = []
    node: DbtLsNode
    for node in selected_nodes:
        if node.resource_type != "model":
            continue
        current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(
            node.unique_id
        )
        reuse_model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(
            node.unique_id
        )
        if current_model is None or reuse_model is None:
            continue
        _raise_if_missing_relation(adapter=adapter, connection=connection, model=reuse_model)
        _raise_if_missing_relation(adapter=adapter, connection=connection, model=current_model)
        schema_result: SchemaDiffResult = adapter.diff_schema(
            connection,
            left=reuse_model.relation_name,
            right=current_model.relation_name,
        )
        row_result: RowDiffResult | None = None
        unequal_row_samples: tuple[Any, ...] = ()
        left_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
        right_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
        bounded_fallback: bool = False
        unique_key: tuple[str, ...] = ()
        excluded_columns: tuple[str, ...] = ()
        if not options.schema_only:
            unique_key = _unique_key(model=current_model)
            cursor_column: str | None = None
            start_cursor: CursorValue | None = None
            end_cursor: CursorValue | None = None
            if options.bounded is not None:
                cursor_column, start_cursor, end_cursor = _bounded_cursors(
                    model=current_model,
                    bounded=options.bounded,
                )
            row_result = adapter.diff_rows(
                connection,
                left=reuse_model.relation_name,
                right=current_model.relation_name,
                unique_key=unique_key,
                excluded_columns=excluded_columns,
                cursor_column=cursor_column,
                start_cursor=start_cursor,
                end_cursor=end_cursor,
            )
            if row_result.unequal_count > 0:
                unequal_row_samples = adapter.sample_unequal_rows(
                    connection,
                    left=reuse_model.relation_name,
                    right=current_model.relation_name,
                    unique_key=unique_key,
                    excluded_columns=excluded_columns,
                    cursor_column=cursor_column,
                    start_cursor=start_cursor,
                    end_cursor=end_cursor,
                    limit=options.max_column_examples * 5,
                )
            if row_result.left_only_count > 0:
                left_only_key_samples = adapter.sample_side_only_rows(
                    connection,
                    left=reuse_model.relation_name,
                    right=current_model.relation_name,
                    unique_key=unique_key,
                    side="left",
                    cursor_column=cursor_column,
                    start_cursor=start_cursor,
                    end_cursor=end_cursor,
                    limit=options.max_row_only_examples,
                )
            if row_result.right_only_count > 0:
                right_only_key_samples = adapter.sample_side_only_rows(
                    connection,
                    left=reuse_model.relation_name,
                    right=current_model.relation_name,
                    unique_key=unique_key,
                    side="right",
                    cursor_column=cursor_column,
                    start_cursor=start_cursor,
                    end_cursor=end_cursor,
                    limit=options.max_row_only_examples,
                )
        results.append(
            ModelDiffResult(
                name=current_model.name,
                left_relation=reuse_model.relation_name,
                right_relation=current_model.relation_name,
                schema_result=schema_result,
                unique_key=unique_key,
                row_result=row_result,
                unequal_row_samples=unequal_row_samples,
                left_only_key_samples=left_only_key_samples,
                right_only_key_samples=right_only_key_samples,
                bounded_fallback=bounded_fallback,
                excluded_columns=excluded_columns,
            )
        )
    return DiffExecutionResult(model_results=tuple(results))


def mode_label(options: DbtDiffOptions) -> str:
    """Return the user-facing dbt diff mode label."""

    if options.schema_only:
        return "schema-only"
    if options.bounded is not None:
        return f"bounded {options.bounded}"
    return "full"


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


def _parse_positive_int(raw_value: str, *, flag: str) -> int:
    try:
        value: int = int(raw_value)
    except ValueError as error:
        raise DbtInteropArgumentError(f"dbt diff {flag} must be positive", code="C202") from error
    if value <= 0:
        raise DbtInteropArgumentError(f"dbt diff {flag} must be positive", code="C202")
    return value


def _dbt_value_flags() -> frozenset[str]:
    return frozenset(
        (
            "--project-dir",
            "--profiles-dir",
            "--profile",
            "--target",
            "--target-path",
            "--state",
            "--indirect-selection",
            "--vars",
            "--threads",
        )
    )


def _dbt_bool_flags() -> frozenset[str]:
    return frozenset(("--defer",))


def _raise_if_missing_relation(
    *, adapter: BaseAdapter, connection: Any, model: DbtManifestModel
) -> None:
    if adapter.relation_exists(
        connection,
        database=model.database,
        schema=model.schema,
        name=model.alias or model.name,
    ):
        return
    raise DbtInteropConfigError(
        f"dbt diff relation for model '{model.name}' does not exist: {model.relation_name}",
        code="C340",
        help=(
            "Build the current dbt model and ensure the production relation exists before diffing."
        ),
    )


def _unique_key(*, model: DbtManifestModel) -> tuple[str, ...]:
    config: dict[str, object] = _config(model=model)
    raw_unique_key: object | None = config.get("unique_key")
    if isinstance(raw_unique_key, str) and raw_unique_key:
        return (raw_unique_key,)
    if isinstance(raw_unique_key, list) and all(
        isinstance(value, str) and value for value in raw_unique_key
    ):
        return tuple(str(value) for value in raw_unique_key)
    raise DbtInteropConfigError(
        f"dbt diff requires model '{model.name}' to define config.unique_key for row comparison",
        code="C341",
        help="Add unique_key to the dbt model config, or run sqb dbt diff --schema-only.",
    )


def _bounded_cursors(
    *, model: DbtManifestModel, bounded: str
) -> tuple[str, CursorValue, CursorValue | None]:
    metadata: dict[str, object] = _sqlbuild_meta(model=model)
    raw_cursor: object | None = metadata.get("cursor")
    raw_cursor_type: object | None = metadata.get("cursor_type")
    if not isinstance(raw_cursor, str) or not raw_cursor:
        raise _bounded_metadata_error(model=model)
    if raw_cursor_type == CursorKind.INTEGER:
        return (
            raw_cursor,
            CursorValue(kind=CursorKind.INTEGER, value=_parse_integer_bound(bounded)),
            None,
        )
    if raw_cursor_type == CursorKind.TIMESTAMP:
        end: datetime = datetime.now(tz=UTC)
        start: datetime = end - _parse_duration_bound(bounded)
        return (
            raw_cursor,
            CursorValue(kind=CursorKind.TIMESTAMP, value=start),
            CursorValue(kind=CursorKind.TIMESTAMP, value=end),
        )
    raise _bounded_metadata_error(model=model)


def _bounded_metadata_error(*, model: DbtManifestModel) -> DbtInteropConfigError:
    return DbtInteropConfigError(
        f"dbt diff --bounded requires model '{model.name}' to define SQLBuild cursor metadata",
        code="C342",
        help=(
            "Add meta.sqlbuild.cursor and meta.sqlbuild.cursor_type to the dbt model, "
            "or run --full / --schema-only."
        ),
    )


def _config(*, model: DbtManifestModel) -> dict[str, object]:
    raw_config: object | None = model.payload.get("config")
    if isinstance(raw_config, dict):
        return {str(key): value for key, value in raw_config.items()}
    return {}


def _sqlbuild_meta(*, model: DbtManifestModel) -> dict[str, object]:
    raw_meta: object | None = model.payload.get("meta")
    if not isinstance(raw_meta, dict):
        raw_meta = _config(model=model).get("meta")
    if not isinstance(raw_meta, dict):
        return {}
    meta: dict[str, object] = {str(key): value for key, value in raw_meta.items()}
    raw_sqlbuild: object | None = meta.get("sqlbuild")
    if not isinstance(raw_sqlbuild, dict):
        return {}
    return {str(key): value for key, value in raw_sqlbuild.items()}


def _parse_integer_bound(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as error:
        raise DbtInteropArgumentError(
            "integer cursor bounded dbt diff requires an integer bound",
            code="C343",
        ) from error


def _parse_duration_bound(raw: str) -> timedelta:
    if len(raw) < 2:
        raise DbtInteropArgumentError(
            "timestamp cursor bounded dbt diff requires duration like 30d, 12h, or 15m",
            code="C344",
        )
    amount_text: str = raw[:-1]
    unit: str = raw[-1]
    try:
        amount: int = int(amount_text)
    except ValueError as error:
        raise DbtInteropArgumentError(
            "timestamp cursor bounded dbt diff requires duration like 30d, 12h, or 15m",
            code="C344",
        ) from error
    if amount <= 0:
        raise DbtInteropArgumentError("bounded dbt diff duration must be positive", code="C345")
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    raise DbtInteropArgumentError(
        "timestamp cursor bounded dbt diff requires duration like 30d, 12h, or 15m",
        code="C344",
    )
