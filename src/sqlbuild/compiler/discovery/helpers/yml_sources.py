"""Parsing helpers for authored sources/*.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SourceParseError
from sqlbuild.compiler.discovery.helpers.yml_primitives import (
    optional_bool,
    optional_mapping,
    optional_non_empty_string,
    parse_audit_instances,
    require_non_empty_string,
)
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry


def parse_sources_yml(contents: str, file_path: Path) -> tuple[SourceEntry, ...]:
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
    expression: str | None = optional_non_empty_string(
        entry=entry,
        key="expression",
        file_path=file_path,
        label="source",
        error_class=SourceParseError,
    )
    if type_enforcement is None and any(column.type is not None for column in columns):
        type_enforcement = True

    source_entry: SourceEntry = SourceEntry(
        name=require_non_empty_string(
            entry=entry,
            key="name",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
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
        expression=expression,
        description=optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="source",
            error_class=SourceParseError,
        ),
        type_enforcement=type_enforcement,
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


def _validate_source_entry(entry: SourceEntry, file_path: Path) -> None:
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
        parsed_columns.append(
            SourceColumnEntry(
                name=require_non_empty_string(
                    entry=column,
                    key="name",
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
                type=optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
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
                audits=parse_audit_instances(
                    entry=column,
                    file_path=file_path,
                    label=column_label,
                    error_class=SourceParseError,
                ),
            )
        )
    return tuple(parsed_columns)
