"""Parsing helpers for authored schema.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SchemaParseError
from sqlbuild.compiler.discovery.helpers.yml_primitives import (
    optional_bool,
    optional_mapping,
    optional_non_empty_string,
    parse_audit_instances,
    require_non_empty_string,
)
from sqlbuild.spec.models.schema import (
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
)


def parse_schema_yml(
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
        meta=optional_mapping(
            entry=entry, key="meta", file_path=file_path, label="seed", error_class=SchemaParseError
        ),
        columns=columns,
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
        parsed_columns.append(
            SchemaColumn(
                name=require_non_empty_string(
                    entry=column,
                    key="name",
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
                type=optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
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
                audits=parse_audit_instances(
                    entry=column,
                    file_path=file_path,
                    label=column_label,
                    error_class=SchemaParseError,
                ),
            )
        )
    return tuple(parsed_columns)
