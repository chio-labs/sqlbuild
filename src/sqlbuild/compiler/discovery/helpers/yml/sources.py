"""Parsing helpers for authored sources/*.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SourceParseError
from sqlbuild.compiler.discovery.helpers.integrations.loaders import (
    integration_loader_name,
    parse_dlt_sources,
    parse_source_integration_loader,
)
from sqlbuild.compiler.discovery.helpers.yml.primitives import (
    optional_bool,
    optional_mapping,
    optional_non_empty_string,
    parse_audit_instances,
    require_non_empty_string,
)
from sqlbuild.spec.models.schema import SchemaAuditInstance
from sqlbuild.spec.models.source import (
    IntegrationLoaderConfig,
    SourceColumnEntry,
    SourceEntry,
    SourceFreshnessAgePolicy,
    SourceFreshnessConfig,
)
from sqlbuild.spec.models.types import (
    SourceFreshnessStrategy,
    SourceFreshnessValueKind,
    SourceWriteStrategy,
)

_SOURCE_WRITE_STRATEGIES: frozenset[str] = frozenset(
    strategy.value for strategy in SourceWriteStrategy
)
_SOURCE_FRESHNESS_STRATEGIES: frozenset[str] = frozenset(
    strategy.value for strategy in SourceFreshnessStrategy
)
_SOURCE_FRESHNESS_VALUE_KINDS: frozenset[str] = frozenset(
    value_kind.value for value_kind in SourceFreshnessValueKind
)


def parse_sources_yml(contents: str, *, file_path: Path) -> tuple[SourceEntry, ...]:
    """Parse one sources/*.yml file into raw source declarations."""

    payload: dict[str, object] = _load_sources_payload(contents=contents, file_path=file_path)
    raw_sources: object = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise SourceParseError(f"{file_path} sources must be a list")

    parsed_sources: list[SourceEntry] = []
    raw_source: object
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise SourceParseError(f"{file_path} sources must contain only mappings")
        parsed_sources.append(
            _parse_source_entry(entry=cast(dict[str, object], raw_source), file_path=file_path)
        )
    parsed_sources.extend(parse_dlt_sources(payload=payload, file_path=file_path))
    return tuple(parsed_sources)


def _load_sources_payload(*, contents: str, file_path: Path) -> dict[str, object]:
    try:
        payload: object = yaml.safe_load(contents)
    except YAMLError as error:
        raise SourceParseError(f"{file_path} contains invalid YAML: {error}") from error
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise SourceParseError(f"{file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _parse_source_entry(*, entry: dict[str, object], file_path: Path) -> SourceEntry:
    columns: tuple[SourceColumnEntry, ...] = _parse_columns(entry=entry, file_path=file_path)
    raw_type_enforcement: bool | None = optional_bool(
        entry=entry,
        key="type_enforcement",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    type_enforcement: bool | None = raw_type_enforcement
    contract: str | None = optional_non_empty_string(
        entry=entry,
        key="contract",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    if contract is not None and contract not in {"enforced", "none"}:
        raise SourceParseError(f"{file_path} source 'contract' must be one of: enforced, none")
    expression: str | None = optional_non_empty_string(
        entry=entry,
        key="expression",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    if type_enforcement is None and any(column.type is not None for column in columns):
        type_enforcement = True

    if "loader" in entry:
        raise SourceParseError(
            f"{file_path} source 'loader' is not supported; use managed: true and name "
            "the terminal loader after the source"
        )
    source_name: str = require_non_empty_string(
        entry=entry,
        key="name",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    integration_loader: IntegrationLoaderConfig | None = parse_source_integration_loader(
        entry=entry, file_path=file_path
    )
    managed: bool = bool(
        optional_bool(
            entry=entry,
            key="managed",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        )
    )
    resolved_loader: str | None = source_name if managed else None
    if resolved_loader is None and integration_loader is not None:
        resolved_loader = integration_loader_name(
            kind=integration_loader.kind,
            source_name=source_name,
        )
        managed = True

    source_entry: SourceEntry = SourceEntry(
        name=source_name,
        database=optional_non_empty_string(
            entry=entry,
            key="database",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        schema=optional_non_empty_string(
            entry=entry,
            key="schema",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        table=optional_non_empty_string(
            entry=entry,
            key="table",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        managed=managed,
        loader=resolved_loader,
        integration_loader=integration_loader,
        freshness=_optional_freshness_config(entry=entry, file_path=file_path),
        write_strategy=_optional_write_strategy(entry=entry, file_path=file_path),
        load_batch_size=_optional_positive_int(
            entry=entry,
            key="load_batch_size",
            file_path=file_path,
        ),
        cursor_column=optional_non_empty_string(
            entry=entry,
            key="cursor_column",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        unique_key=_optional_unique_key(entry=entry, file_path=file_path),
        expression=expression,
        description=optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        type_enforcement=type_enforcement,
        contract=contract,
        meta=optional_mapping(
            entry=entry,
            key="meta",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        columns=columns,
        audits=parse_audit_instances(
            entry=entry, file_path=file_path, label="source", error_class=SourceParseError
        ),
    )
    _validate_source_entry(entry=source_entry, file_path=file_path)
    return source_entry


def _validate_source_entry(entry: SourceEntry, *, file_path: Path) -> None:
    relation_keys: tuple[str, ...] = tuple(
        key
        for key, value in (
            ("database", entry.database),
            ("schema", entry.schema),
            ("table", entry.table),
        )
        if value is not None
    )
    if entry.expression is not None and relation_keys:
        keys: str = ", ".join(relation_keys)
        raise SourceParseError(
            f"{file_path} source '{entry.name}' cannot define expression with {keys}"
        )
    if entry.expression is not None and entry.type_enforcement:
        typed_columns: tuple[SourceColumnEntry, ...] = tuple(
            column for column in entry.columns if column.type is not None
        )
        if not typed_columns:
            raise SourceParseError(
                f"{file_path} source '{entry.name}' uses expression with type_enforcement "
                "but has no typed columns"
            )
    if entry.integration_loader is not None:
        expected_loader_name: str = integration_loader_name(
            kind=entry.integration_loader.kind, source_name=entry.name
        )
        if entry.loader != expected_loader_name:
            raise SourceParseError(
                f"{file_path} source '{entry.name}' cannot override loader for "
                f"{entry.integration_loader.kind}"
            )
        if entry.write_strategy is not None:
            raise SourceParseError(
                f"{file_path} source '{entry.name}' cannot define write_strategy with "
                f"{entry.integration_loader.kind}"
            )
    if entry.write_strategy is not None and entry.loader is None:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' defines write_strategy but is not managed"
        )
    if entry.write_strategy == SourceWriteStrategy.APPEND and entry.unique_key:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' unique_key is not supported with "
            "write_strategy append"
        )
    if entry.write_strategy == SourceWriteStrategy.MERGE and not entry.unique_key:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' write_strategy merge requires unique_key"
        )
    if entry.write_strategy == SourceWriteStrategy.TABLE and entry.cursor_column is not None:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' cursor_column is not supported with "
            "write_strategy table"
        )
    if entry.write_strategy == SourceWriteStrategy.TABLE and entry.unique_key:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' unique_key is not supported with "
            "write_strategy table"
        )
    if entry.write_strategy == SourceWriteStrategy.DELETE_INSERT and entry.cursor_column is None:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' write_strategy delete_insert requires cursor_column"
        )
    if entry.write_strategy == SourceWriteStrategy.DELETE_INSERT and entry.unique_key:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' unique_key is not supported with "
            "write_strategy delete_insert"
        )
    if entry.cursor_column is not None and entry.write_strategy not in {
        SourceWriteStrategy.APPEND,
        SourceWriteStrategy.DELETE_INSERT,
        SourceWriteStrategy.MERGE,
    }:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' cursor_column requires write_strategy "
            "append, delete_insert, or merge"
        )
    if entry.unique_key and entry.write_strategy != SourceWriteStrategy.MERGE:
        raise SourceParseError(
            f"{file_path} source '{entry.name}' unique_key requires write_strategy merge"
        )


def _optional_unique_key(*, entry: dict[str, object], file_path: Path) -> tuple[str, ...]:
    value: object | None = entry.get("unique_key")
    if value is None:
        return ()
    if isinstance(value, str):
        stripped: str = value.strip()
        if not stripped:
            raise SourceParseError(f"{file_path} source 'unique_key' must be non-empty")
        return (stripped,)
    if isinstance(value, list):
        keys: list[str] = []
        item: object
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise SourceParseError(
                    f"{file_path} source 'unique_key' must contain only non-empty strings"
                )
            keys.append(item.strip())
        if not keys:
            raise SourceParseError(f"{file_path} source 'unique_key' must be non-empty")
        return tuple(keys)
    raise SourceParseError(f"{file_path} source 'unique_key' must be a string or list")


def _optional_write_strategy(
    *, entry: dict[str, object], file_path: Path
) -> SourceWriteStrategy | None:
    value: str | None = optional_non_empty_string(
        entry=entry,
        key="write_strategy",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    if value is None:
        return None
    if value not in _SOURCE_WRITE_STRATEGIES:
        strategies: str = ", ".join(sorted(_SOURCE_WRITE_STRATEGIES))
        raise SourceParseError(f"{file_path} source write_strategy must be one of: {strategies}")
    return SourceWriteStrategy(value)


def _optional_freshness_config(
    *, entry: dict[str, object], file_path: Path
) -> SourceFreshnessConfig | None:
    raw_freshness: object | None = entry.get("freshness")
    if raw_freshness is None:
        return None
    if not isinstance(raw_freshness, dict):
        raise SourceParseError(f"{file_path} source 'freshness' must be a mapping")
    freshness: dict[str, object] = cast(dict[str, object], raw_freshness)
    raw_strategy: str = require_non_empty_string(
        entry=freshness,
        key="strategy",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    if raw_strategy not in _SOURCE_FRESHNESS_STRATEGIES:
        strategies: str = ", ".join(sorted(_SOURCE_FRESHNESS_STRATEGIES))
        raise SourceParseError(
            f"{file_path} source freshness 'strategy' must be one of: {strategies}"
        )
    strategy: SourceFreshnessStrategy = SourceFreshnessStrategy(raw_strategy)
    raw_value_kind: str | None = optional_non_empty_string(
        entry=freshness,
        key="type",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    value_kind: SourceFreshnessValueKind | None = None
    if raw_value_kind is not None:
        if raw_value_kind not in _SOURCE_FRESHNESS_VALUE_KINDS:
            value_kinds: str = ", ".join(sorted(_SOURCE_FRESHNESS_VALUE_KINDS))
            raise SourceParseError(
                f"{file_path} source freshness 'type' must be one of: {value_kinds}"
            )
        value_kind = SourceFreshnessValueKind(raw_value_kind)
    column: str | None = optional_non_empty_string(
        entry=freshness,
        key="column",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    query: str | None = optional_non_empty_string(
        entry=freshness,
        key="query",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    freshness_filter: str | None = optional_non_empty_string(
        entry=freshness,
        key="filter",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    lag_tolerance: str | None = optional_non_empty_string(
        entry=freshness,
        key="lag_tolerance",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    age_policy: SourceFreshnessAgePolicy | None = _optional_freshness_age_policy(
        freshness=freshness,
        file_path=file_path,
    )
    config: SourceFreshnessConfig = SourceFreshnessConfig(
        strategy=strategy,
        value_kind=value_kind,
        column=column,
        query=query,
        filter=freshness_filter,
        lag_tolerance=lag_tolerance,
        age_policy=age_policy,
    )
    _validate_freshness_config(config=config, file_path=file_path)
    return config


def _validate_freshness_config(*, config: SourceFreshnessConfig, file_path: Path) -> None:
    if config.lag_tolerance is not None:
        _validate_source_freshness_lag_tolerance(config=config, file_path=file_path)
    if config.age_policy is not None:
        _validate_source_freshness_age_policy(config=config, file_path=file_path)
    if config.strategy == SourceFreshnessStrategy.ADAPTER:
        if (
            config.value_kind is not None
            or config.column is not None
            or config.query is not None
            or config.filter is not None
        ):
            raise SourceParseError(
                f"{file_path} source freshness strategy adapter does not support type, "
                "column, query, or filter"
            )
        return
    if config.strategy == SourceFreshnessStrategy.COLUMN:
        if config.column is None:
            raise SourceParseError(f"{file_path} source freshness strategy column requires column")
        if not config.column.replace("_", "").isalnum() or config.column[0].isdigit():
            raise SourceParseError(
                f"{file_path} source freshness column must be a plain column name; "
                "use strategy sql for expressions"
            )
        if config.value_kind is None:
            raise SourceParseError(f"{file_path} source freshness strategy column requires type")
        if config.query is not None:
            raise SourceParseError(
                f"{file_path} source freshness strategy column does not support query"
            )
        return
    if config.query is None:
        raise SourceParseError(f"{file_path} source freshness strategy sql requires query")
    if config.value_kind is None:
        raise SourceParseError(f"{file_path} source freshness strategy sql requires type")
    if config.column is not None:
        raise SourceParseError(f"{file_path} source freshness strategy sql does not support column")
    if config.filter is not None:
        raise SourceParseError(f"{file_path} source freshness strategy sql does not support filter")


def _optional_freshness_age_policy(
    *, freshness: dict[str, object], file_path: Path
) -> SourceFreshnessAgePolicy | None:
    if "age_policy" not in freshness:
        return None
    age_policy: dict[str, object] = optional_mapping(
        entry=freshness,
        key="age_policy",
        file_path=file_path,
        label="source freshness",
        error_class=SourceParseError,
    )
    warn_after: str | None = optional_non_empty_string(
        entry=age_policy,
        key="warn_after",
        file_path=file_path,
        label="source freshness age_policy",
        error_class=SourceParseError,
    )
    error_after: str | None = optional_non_empty_string(
        entry=age_policy,
        key="error_after",
        file_path=file_path,
        label="source freshness age_policy",
        error_class=SourceParseError,
    )
    if warn_after is None and error_after is None:
        raise SourceParseError(
            f"{file_path} source freshness age_policy requires warn_after or error_after"
        )
    return SourceFreshnessAgePolicy(warn_after=warn_after, error_after=error_after)


def _validate_source_freshness_lag_tolerance(
    *, config: SourceFreshnessConfig, file_path: Path
) -> None:
    if config.value_kind is not SourceFreshnessValueKind.TIMESTAMP:
        raise SourceParseError(
            f"{file_path} source freshness lag_tolerance requires type timestamp"
        )
    raw: str = config.lag_tolerance or ""
    if not _is_valid_source_freshness_duration(raw):
        raise SourceParseError(
            f"{file_path} source freshness lag_tolerance must be a positive duration like "
            "15m, 2h, or 1d"
        )


def _validate_source_freshness_age_policy(
    *, config: SourceFreshnessConfig, file_path: Path
) -> None:
    if (
        config.strategy != SourceFreshnessStrategy.ADAPTER
        and config.value_kind is not SourceFreshnessValueKind.TIMESTAMP
    ):
        raise SourceParseError(f"{file_path} source freshness age_policy requires type timestamp")
    policy: SourceFreshnessAgePolicy = config.age_policy or SourceFreshnessAgePolicy()
    warn_after: str | None = policy.warn_after
    error_after: str | None = policy.error_after
    for raw in (warn_after, error_after):
        if raw is not None and not _is_valid_source_freshness_duration(raw):
            raise SourceParseError(
                f"{file_path} source freshness age_policy values must be positive durations like "
                "15m, 2h, or 1d"
            )
    if warn_after is not None and error_after is not None:
        if _source_freshness_duration_minutes(warn_after) > _source_freshness_duration_minutes(
            error_after
        ):
            raise SourceParseError(
                f"{file_path} source freshness age_policy warn_after must be less than or "
                "equal to error_after"
            )


def _is_valid_source_freshness_duration(value: str) -> bool:
    if len(value) < 2:
        return False
    unit: str = value[-1]
    amount: str = value[:-1]
    return unit in {"m", "h", "d"} and amount.isdigit() and int(amount) > 0


def _source_freshness_duration_minutes(value: str) -> int:
    amount: int = int(value[:-1])
    unit: str = value[-1]
    if unit == "d":
        return amount * 24 * 60
    if unit == "h":
        return amount * 60
    return amount


def _optional_positive_int(*, entry: dict[str, object], key: str, file_path: Path) -> int | None:
    value: object | None = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SourceParseError(f"{file_path} source '{key}' must be a positive integer")
    return value


def _parse_columns(*, entry: dict[str, object], file_path: Path) -> tuple[SourceColumnEntry, ...]:
    raw_columns: object = entry.get("columns", [])
    if not isinstance(raw_columns, list):
        raise SourceParseError(f"{file_path} source columns must be a list")

    parsed_columns: list[SourceColumnEntry] = []
    raw_column: object
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            raise SourceParseError(f"{file_path} source columns must contain only mappings")
        column: dict[str, object] = cast(dict[str, object], raw_column)
        column_label: str = "source column"
        column_name: str = require_non_empty_string(
            entry=column,
            key="name",
            file_path=file_path,
            label=column_label,
            error_class=SourceParseError,
        )
        nullable: bool | None = optional_bool(
            entry=column,
            key="nullable",
            file_path=file_path,
            label=column_label,
            error_class=SourceParseError,
        )
        audits: tuple[SchemaAuditInstance, ...] = parse_audit_instances(
            entry=column,
            file_path=file_path,
            label=column_label,
            error_class=SourceParseError,
        )
        _validate_nullable_audits(
            file_path=file_path,
            column_name=column_name,
            nullable=nullable,
            audit_names=tuple(audit.definition_name for audit in audits),
        )
        parsed_columns.append(
            SourceColumnEntry(
                name=column_name,
                type=optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
                nullable=nullable,
                description=optional_non_empty_string(
                    entry=column,
                    key="description",
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
                meta=optional_mapping(
                    entry=column,
                    key="meta",
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
                audits=audits,
            )
        )
    return tuple(parsed_columns)


def _validate_nullable_audits(
    *, file_path: Path, column_name: str, nullable: bool | None, audit_names: tuple[str, ...]
) -> None:
    if nullable is True and "not_null" in audit_names:
        raise SourceParseError(
            f"{file_path} column '{column_name}' cannot set nullable = true and audit not_null"
        )
