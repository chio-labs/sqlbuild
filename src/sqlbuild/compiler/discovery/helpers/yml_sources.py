"""Parsing helpers for authored sources/*.yml files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SourceParseError
from sqlbuild.spec.models.schema import SchemaAuditInstance
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
    return SourceEntry(
        name=_require_non_empty_string(
            entry=entry, key="name", file_path=file_path, label="source"
        ),
        database=_optional_non_empty_string(
            entry=entry,
            key="database",
            file_path=file_path,
            label="source",
        ),
        schema=_optional_non_empty_string(
            entry=entry,
            key="schema",
            file_path=file_path,
            label="source",
        ),
        table=_optional_non_empty_string(
            entry=entry,
            key="table",
            file_path=file_path,
            label="source",
        ),
        description=_optional_non_empty_string(
            entry=entry,
            key="description",
            file_path=file_path,
            label="source",
        ),
        type_enforcement=_optional_bool(
            entry=entry,
            key="type_enforcement",
            file_path=file_path,
            label="source",
        ),
        meta=_optional_mapping(entry=entry, key="meta", file_path=file_path, label="source"),
        columns=_parse_columns(entry=entry, file_path=file_path),
        audits=_parse_audit_instances(entry=entry, file_path=file_path, label="source"),
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
        parsed_columns.append(
            SourceColumnEntry(
                name=_require_non_empty_string(
                    entry=column,
                    key="name",
                    file_path=file_path,
                    label="source column",
                ),
                type=_optional_non_empty_string(
                    entry=column,
                    key="type",
                    file_path=file_path,
                    label="source column",
                ),
                description=_optional_non_empty_string(
                    entry=column,
                    key="description",
                    file_path=file_path,
                    label="source column",
                ),
                meta=_optional_mapping(
                    entry=column,
                    key="meta",
                    file_path=file_path,
                    label="source column",
                ),
                audits=_parse_audit_instances(
                    entry=column,
                    file_path=file_path,
                    label="source column",
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
        raise SourceParseError(f"{file_path} {label} audits must be a list")

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
            raise SourceParseError(f"{file_path} {label} audits must not contain empty names")
        return SchemaAuditInstance(definition_name=raw_audit)

    if not isinstance(raw_audit, dict) or len(raw_audit) != 1:
        raise SourceParseError(f"{file_path} {label} audits must be strings or single-key mappings")

    typed_audit_mapping: dict[str, object] = cast(dict[str, object], raw_audit)
    definition_name: str = next(iter(typed_audit_mapping))
    if not isinstance(definition_name, str) or not definition_name.strip():
        raise SourceParseError(f"{file_path} {label} audit names must be non-empty strings")

    raw_arguments: object = typed_audit_mapping[definition_name]
    if raw_arguments is None:
        return SchemaAuditInstance(definition_name=definition_name)
    if not isinstance(raw_arguments, dict):
        raise SourceParseError(
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
        raise SourceParseError(f"{file_path} {label} must define non-empty string '{key}'")
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
        raise SourceParseError(f"{file_path} {label} '{key}' must be a non-empty string")
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
        raise SourceParseError(f"{file_path} {label} '{key}' must be a mapping")
    return cast(dict[str, object], raw_value)


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
        raise SourceParseError(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value
