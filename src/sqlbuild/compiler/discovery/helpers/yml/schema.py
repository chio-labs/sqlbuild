"""Parsing helpers for authored schema.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.constants import NOT_NULL_AUDIT_NAME, SEEDS_DIRECTORY_NAME
from sqlbuild.compiler.discovery.exceptions import SchemaParseError
from sqlbuild.compiler.discovery.helpers.yml.primitives import (
    optional_bool,
    optional_mapping,
    optional_non_empty_string,
    optional_string_tuple,
    parse_audit_instances,
    require_non_empty_string,
)
from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SeedCsvSettings,
)

_SEED_CSV_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "delimiter",
        "quotechar",
        "doublequote",
        "escapechar",
        "skipinitialspace",
        "lineterminator",
        "encoding",
        "na_values",
        "keep_default_na",
    }
)
_SEED_CSV_STRING_SETTINGS: frozenset[str] = frozenset(
    {"delimiter", "quotechar", "escapechar", "lineterminator", "encoding"}
)
_SEED_CSV_BOOL_SETTINGS: frozenset[str] = frozenset(
    {"doublequote", "skipinitialspace", "keep_default_na"}
)


def parse_schema_yml(
    *,
    contents: str,
    file_path: Path,
) -> tuple[tuple[SchemaModelEntry, ...], tuple[SchemaSeedEntry, ...]]:
    """Parse one schema.yml file into raw model and seed metadata."""

    payload: dict[str, object] = _load_schema_payload(contents=contents, file_path=file_path)
    return (
        _parse_model_entries(payload=payload, file_path=file_path),
        _parse_seed_entries(payload=payload, file_path=file_path),
    )


def _load_schema_payload(*, contents: str, file_path: Path) -> dict[str, object]:
    try:
        payload: object = yaml.safe_load(contents)
    except YAMLError as error:
        raise SchemaParseError(f"{file_path} contains invalid YAML: {error}") from error
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise SchemaParseError(f"{file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _parse_model_entries(
    *, payload: dict[str, object], file_path: Path
) -> tuple[SchemaModelEntry, ...]:
    raw_models: object = payload.get("models", [])
    if raw_models:
        raise SchemaParseError(
            f"{file_path} declares model metadata in 'models', but model metadata must live "
            "in the model file MODEL(...). Move description, columns, and audits into the "
            "model header."
        )
    model_mappings: tuple[dict[str, object], ...] = _parse_named_mapping_list(
        raw_value=raw_models,
        file_path=file_path,
        label="models",
    )
    return tuple(_parse_model_entry(entry=entry, file_path=file_path) for entry in model_mappings)


def _parse_seed_entries(
    *, payload: dict[str, object], file_path: Path
) -> tuple[SchemaSeedEntry, ...]:
    raw_seeds: object = payload.get("seeds", [])
    if raw_seeds and SEEDS_DIRECTORY_NAME not in file_path.parts:
        raise SchemaParseError(
            f"{file_path} declares seeds, but seed declarations must live under seeds/**/*.yml"
        )
    seed_mappings: tuple[dict[str, object], ...] = _parse_named_mapping_list(
        raw_value=raw_seeds,
        file_path=file_path,
        label="seeds",
    )
    return tuple(_parse_seed_entry(entry=entry, file_path=file_path) for entry in seed_mappings)


def _parse_named_mapping_list(
    *,
    raw_value: object,
    file_path: Path,
    label: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_value, list):
        raise SchemaParseError(f"{file_path} {label} must be a list")

    parsed_entries: list[dict[str, object]] = []
    entry: object
    for entry in raw_value:
        if not isinstance(entry, dict):
            raise SchemaParseError(f"{file_path} {label} must contain only mappings")
        parsed_entries.append(cast(dict[str, object], entry))
    return tuple(parsed_entries)


def _parse_model_entry(*, entry: dict[str, object], file_path: Path) -> SchemaModelEntry:
    return SchemaModelEntry(
        name=require_non_empty_string(
            entry=entry,
            key="name",
            file_path=file_path,
            label="model",
            error_class=SchemaParseError,
        ),
        description=optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="model",
            error_class=SchemaParseError,
        ),
        type_enforcement=optional_bool(
            entry=entry,
            key="type_enforcement",
            file_path=file_path,
            label="model",
            error_class=SchemaParseError,
        ),
        meta=optional_mapping(
            entry=entry,
            key="meta",
            file_path=file_path,
            label="model",
            error_class=SchemaParseError,
        ),
        columns=_parse_columns(entry=entry, file_path=file_path, label="model"),
        audits=parse_audit_instances(
            entry=entry, file_path=file_path, label="model", error_class=SchemaParseError
        ),
        tags=optional_string_tuple(
            entry=entry,
            key="tags",
            file_path=file_path,
            label="model",
            error_class=SchemaParseError,
        ),
    )


def _parse_seed_entry(*, entry: dict[str, object], file_path: Path) -> SchemaSeedEntry:
    columns: tuple[SchemaColumn, ...] = _parse_columns(
        entry=entry, file_path=file_path, label="seed"
    )
    if not columns:
        raise SchemaParseError(f"{file_path} seed must declare at least one column")

    column: SchemaColumn
    for column in columns:
        if column.type is None:
            raise SchemaParseError(
                f"{file_path} seed column '{column.name}' must define non-empty string 'type'"
            )

    return SchemaSeedEntry(
        name=require_non_empty_string(
            entry=entry, key="name", file_path=file_path, label="seed", error_class=SchemaParseError
        ),
        description=optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="seed",
            error_class=SchemaParseError,
        ),
        database=optional_non_empty_string(
            entry=entry,
            key="database",
            file_path=file_path,
            label="seed",
            error_class=SchemaParseError,
        ),
        schema=optional_non_empty_string(
            entry=entry,
            key="schema",
            file_path=file_path,
            label="seed",
            error_class=SchemaParseError,
        ),
        meta=optional_mapping(
            entry=entry, key="meta", file_path=file_path, label="seed", error_class=SchemaParseError
        ),
        csv_settings=_parse_seed_csv_settings(entry=entry, file_path=file_path),
        columns=columns,
    )


def _parse_seed_csv_settings(*, entry: dict[str, object], file_path: Path) -> SeedCsvSettings:
    raw_settings: object | None = entry.get("csv_settings")
    if raw_settings is None:
        return SeedCsvSettings()
    if not isinstance(raw_settings, dict):
        raise SchemaParseError(f"{file_path} seed 'csv_settings' must be a mapping")
    settings: dict[str, object] = cast(dict[str, object], raw_settings)
    unknown_keys: set[str] = set(settings) - set(_SEED_CSV_SETTING_KEYS)
    if unknown_keys:
        raise SchemaParseError(
            f"{file_path} seed 'csv_settings' has unknown keys: {', '.join(sorted(unknown_keys))}"
        )

    key: str
    for key in _SEED_CSV_STRING_SETTINGS:
        value: object | None = settings.get(key)
        if value is not None and not isinstance(value, str):
            raise SchemaParseError(f"{file_path} seed csv_settings '{key}' must be a string")
    for key in _SEED_CSV_BOOL_SETTINGS:
        value = settings.get(key)
        if value is not None and not isinstance(value, bool):
            raise SchemaParseError(f"{file_path} seed csv_settings '{key}' must be a boolean")

    na_values: tuple[object, ...] | dict[str, tuple[object, ...]] | None = _parse_na_values(
        raw_value=settings.get("na_values"), file_path=file_path
    )
    return SeedCsvSettings(
        delimiter=cast(str | None, settings.get("delimiter")),
        quotechar=cast(str | None, settings.get("quotechar")),
        doublequote=cast(bool | None, settings.get("doublequote")),
        escapechar=cast(str | None, settings.get("escapechar")),
        skipinitialspace=cast(bool | None, settings.get("skipinitialspace")),
        lineterminator=cast(str | None, settings.get("lineterminator")),
        encoding=cast(str | None, settings.get("encoding")),
        na_values=na_values,
        keep_default_na=cast(bool | None, settings.get("keep_default_na")),
    )


def _parse_na_values(
    *, raw_value: object | None, file_path: Path
) -> tuple[object, ...] | dict[str, tuple[object, ...]] | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, list):
        return tuple(_validate_na_scalar(value=value, file_path=file_path) for value in raw_value)
    if isinstance(raw_value, dict):
        parsed: dict[str, tuple[object, ...]] = {}
        raw_mapping: dict[str, object] = cast(dict[str, object], raw_value)
        column_name: str
        values: object
        for column_name, values in raw_mapping.items():
            if not isinstance(values, list):
                raise SchemaParseError(
                    f"{file_path} seed csv_settings 'na_values' mapping values must be lists"
                )
            parsed[column_name] = tuple(
                _validate_na_scalar(value=value, file_path=file_path) for value in values
            )
        return parsed
    raise SchemaParseError(f"{file_path} seed csv_settings 'na_values' must be a list or mapping")


def _validate_na_scalar(*, value: object, file_path: Path) -> object:
    if value is None or isinstance(value, str | int | bool):
        return value
    raise SchemaParseError(
        f"{file_path} seed csv_settings 'na_values' entries must be strings, integers, "
        "booleans, or null"
    )


def _parse_columns(
    *,
    entry: dict[str, object],
    file_path: Path,
    label: str,
) -> tuple[SchemaColumn, ...]:
    raw_columns: object = entry.get("columns", [])
    if not isinstance(raw_columns, list):
        raise SchemaParseError(f"{file_path} {label} columns must be a list")

    parsed_columns: list[SchemaColumn] = []
    raw_column: object
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            raise SchemaParseError(f"{file_path} {label} columns must contain only mappings")
        column: dict[str, object] = cast(dict[str, object], raw_column)
        column_label: str = f"{label} column"
        column_name: str = require_non_empty_string(
            entry=column,
            key="name",
            file_path=file_path,
            label=column_label,
            error_class=SchemaParseError,
        )
        nullable: bool | None = optional_bool(
            entry=column,
            key="nullable",
            file_path=file_path,
            label=column_label,
            error_class=SchemaParseError,
        )
        audits: tuple[SchemaAuditInstance, ...] = parse_audit_instances(
            entry=column,
            file_path=file_path,
            label=column_label,
            error_class=SchemaParseError,
        )
        _validate_nullable_audits(
            file_path=file_path,
            column_name=column_name,
            nullable=nullable,
            audit_names=tuple(audit.definition_name for audit in audits),
        )
        parsed_columns.append(
            SchemaColumn(
                name=column_name,
                type=optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
                nullable=nullable,
                description=optional_non_empty_string(
                    entry=column,
                    key="description",
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
                meta=optional_mapping(
                    entry=column,
                    key="meta",
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
                audits=audits,
            )
        )
    return tuple(parsed_columns)


def _validate_nullable_audits(
    *, file_path: Path, column_name: str, nullable: bool | None, audit_names: tuple[str, ...]
) -> None:
    if nullable is True and NOT_NULL_AUDIT_NAME in audit_names:
        raise SchemaParseError(
            f"{file_path} column '{column_name}' cannot set nullable = true and audit not_null"
        )
