"""Shared YAML field-extraction primitives for discovery parsers."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.spec.models.schema import SchemaAuditInstance


def parse_audit_instances(
    *,
    entry: dict[str, object],
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> tuple[SchemaAuditInstance, ...]:
    """Parse a list of schema-attached audit instances from a YAML entry."""

    raw_audits: object = entry.get("audits", [])
    if not isinstance(raw_audits, list):
        raise error_class(f"{file_path} {label} audits must be a list")

    parsed_audits: list[SchemaAuditInstance] = []
    raw_audit: object
    for raw_audit in raw_audits:
        parsed_audits.append(
            parse_audit_instance(
                raw_audit=raw_audit,
                file_path=file_path,
                label=label,
                error_class=error_class,
            )
        )
    return tuple(parsed_audits)


def parse_audit_instance(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> SchemaAuditInstance:
    """Parse one audit instance from a raw YAML value."""

    if isinstance(raw_audit, str):
        if not raw_audit.strip():
            raise error_class(f"{file_path} {label} audits must not contain empty names")
        return SchemaAuditInstance(definition_name=raw_audit)

    if not isinstance(raw_audit, dict) or len(raw_audit) != 1:
        raise error_class(f"{file_path} {label} audits must be strings or single-key mappings")

    typed_audit_mapping: dict[str, object] = cast(dict[str, object], raw_audit)

    definition_name: str = next(iter(typed_audit_mapping))
    if not isinstance(definition_name, str) or not definition_name.strip():
        raise error_class(f"{file_path} {label} audit names must be non-empty strings")

    raw_arguments: object = typed_audit_mapping[definition_name]
    if raw_arguments is None:
        return SchemaAuditInstance(definition_name=definition_name)
    if not isinstance(raw_arguments, dict):
        raise error_class(
            f"{file_path} {label} audit '{definition_name}' arguments must be a mapping"
        )

    argument_mapping: dict[str, object] = cast(dict[str, object], raw_arguments)
    name: str | None = optional_named_string(
        raw_value=argument_mapping.get("name"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="name",
        error_class=error_class,
    )
    description: str | None = optional_named_string(
        raw_value=argument_mapping.get("description"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="description",
        error_class=error_class,
    )
    severity: str | None = optional_named_string(
        raw_value=argument_mapping.get("severity"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="severity",
        error_class=error_class,
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


def require_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str:
    """Extract a required non-empty string from a YAML mapping."""

    raw_value: object | None = entry.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} must define non-empty string '{key}'")
    return raw_value


def optional_non_empty_string(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> str | None:
    """Extract an optional non-empty string from a YAML mapping."""

    return optional_named_string(
        raw_value=entry.get(key),
        file_path=file_path,
        label=label,
        key=key,
        error_class=error_class,
    )


def optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None:
    """Validate and return an optional named string value."""

    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def optional_bool(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> bool | None:
    """Extract an optional boolean from a YAML mapping."""

    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, bool):
        raise error_class(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value


def optional_mapping(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> dict[str, object]:
    """Extract an optional mapping from a YAML mapping."""

    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise error_class(f"{file_path} {label} '{key}' must be a mapping")
    return cast(dict[str, object], raw_value)


def optional_string_tuple(
    *,
    entry: dict[str, object],
    key: str,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> tuple[str, ...]:
    """Extract an optional list of strings from a YAML mapping."""

    raw_value: object | None = entry.get(key)
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise error_class(f"{file_path} {label} '{key}' must be a list")
    items: list[str] = []
    item: object
    for item in raw_value:
        if not isinstance(item, str):
            raise error_class(f"{file_path} {label} '{key}' entries must be strings")
        items.append(item)
    return tuple(items)
