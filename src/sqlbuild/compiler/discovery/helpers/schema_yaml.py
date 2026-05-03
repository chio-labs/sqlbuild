"""Parsing helpers for authored schema.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SchemaParseError
from sqlbuild.spec.models.schema import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
)


def parse_schema_yaml(
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
        name=_require_non_empty_string(entry=entry, key="name", file_path=file_path, label="model"),
        description=_optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="model",
        ),
        type_enforcement=_optional_bool(
            entry=entry,
            key="type_enforcement",
            file_path=file_path,
            label="model",
        ),
        meta=_optional_mapping(entry=entry, key="meta", file_path=file_path, label="model"),
        columns=_parse_columns(entry=entry, file_path=file_path, label="model"),
        audits=_parse_audit_instances(entry=entry, file_path=file_path, label="model"),
    )


def _parse_seed_entry(*, entry: dict[str, object], file_path: Path) -> SchemaSeedEntry:
    return SchemaSeedEntry(
        name=_require_non_empty_string(entry=entry, key="name", file_path=file_path, label="seed"),
        description=_optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="seed",
        ),
        meta=_optional_mapping(entry=entry, key="meta", file_path=file_path, label="seed"),
        columns=_parse_columns(entry=entry, file_path=file_path, label="seed"),
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
        parsed_columns.append(
            SchemaColumn(
                name=_require_non_empty_string(
                    entry=column,
                    key="name",
                    file_path=file_path,
                    label=f"{label} column",
                ),
                type=_optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label=f"{label} column",
                ),
                description=_optional_non_empty_string(
                    entry=column,
                    key="description",
                    file_path=file_path,
                    label=f"{label} column",
                ),
                meta=_optional_mapping(
                    entry=column,
                    key="meta",
                    file_path=file_path,
                    label=f"{label} column",
                ),
                audits=_parse_audit_instances(
                    entry=column,
                    file_path=file_path,
                    label=f"{label} column",
                ),
            )
        )
    return tuple(parsed_columns)


def _parse_audit_instances(
    *,
    entry: dict[str, object],
    file_path: Path,
    label: str,
) -> tuple[SchemaAuditInstance, ...]:
    raw_audits: object = entry.get("audits", [])
    if not isinstance(raw_audits, list):
        raise SchemaParseError(f"{file_path} {label} audits must be a list")

    parsed_audits: list[SchemaAuditInstance] = []
    raw_audit: object
    for raw_audit in raw_audits:
        parsed_audits.append(
            _parse_audit_instance(raw_audit=raw_audit, file_path=file_path, label=label)
        )
    return tuple(parsed_audits)


def _parse_audit_instance(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
) -> SchemaAuditInstance:
    if isinstance(raw_audit, str):
        if not raw_audit.strip():
            raise SchemaParseError(f"{file_path} {label} audits must not contain empty names")
        return SchemaAuditInstance(definition_name=raw_audit)

    if not isinstance(raw_audit, dict) or len(raw_audit) != 1:
        raise SchemaParseError(f"{file_path} {label} audits must be strings or single-key mappings")

    typed_audit_mapping: dict[str, object] = cast(dict[str, object], raw_audit)

    definition_name: str = next(iter(typed_audit_mapping))
    if not isinstance(definition_name, str) or not definition_name.strip():
        raise SchemaParseError(f"{file_path} {label} audit names must be non-empty strings")

    raw_arguments: object = typed_audit_mapping[definition_name]
    if raw_arguments is None:
        return SchemaAuditInstance(definition_name=definition_name)
    if not isinstance(raw_arguments, dict):
        raise SchemaParseError(
            f"{file_path} {label} audit '{definition_name}' arguments must be a mapping"
        )

    argument_mapping: dict[str, object] = cast(dict[str, object], raw_arguments)
    name: str | None = _optional_named_string(
        raw_value=argument_mapping.get("name"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="name",
    )
    description: str | None = _optional_named_string(
        raw_value=argument_mapping.get("description"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="description",
    )
    severity: str | None = _optional_named_string(
        raw_value=argument_mapping.get("severity"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="severity",
    )
    arguments: dict[str, object] = {
        key: value
        for key, value in argument_mapping.items()
        if key not in {"name", "description", "severity"}
    }
    return SchemaAuditInstance(
        definition_name=definition_name,
        arguments=arguments,
        name=name,
        description=description,
        severity=severity,
    )


def _require_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
) -> str:
    raw_value: object | None = entry.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise SchemaParseError(f"{file_path} {label} must define non-empty string '{key}'")
    return raw_value


def _optional_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
) -> str | None:
    return _optional_named_string(
        raw_value=entry.get(key),
        file_path=file_path,
        label=label,
        key=key,
    )


def _optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise SchemaParseError(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def _optional_bool(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
) -> bool | None:
    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, bool):
        raise SchemaParseError(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value


def _optional_mapping(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
) -> dict[str, object]:
    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise SchemaParseError(f"{file_path} {label} '{key}' must be a mapping")
    return cast(dict[str, object], raw_value)
