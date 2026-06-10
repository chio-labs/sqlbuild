"""Shared parsing helpers for schema-attached audit instances."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.spec.models.schema import SchemaAuditInstance


def parse_audit_instance(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> SchemaAuditInstance:
    """Parse one audit instance from a raw mapping/list value."""

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
    name: str | None = _optional_named_string(
        raw_value=argument_mapping.get("name"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="name",
        error_class=error_class,
    )
    description: str | None = _optional_named_string(
        raw_value=argument_mapping.get("description"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="description",
        error_class=error_class,
    )
    severity: str | None = _optional_named_string(
        raw_value=argument_mapping.get("severity"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="severity",
        error_class=error_class,
    )
    run_scope: str | None = _optional_named_string(
        raw_value=argument_mapping.get("run_scope"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="run_scope",
        error_class=error_class,
    )
    always_run: bool = _optional_named_bool(
        raw_value=argument_mapping.get("always_run"),
        file_path=file_path,
        label=f"{label} audit '{definition_name}'",
        key="always_run",
        error_class=error_class,
    )
    arguments: dict[str, object] = {
        key: value
        for key, value in argument_mapping.items()
        if key not in {"name", "description", "severity", "run_scope", "always_run"}
    }
    return SchemaAuditInstance(
        definition_name=definition_name,
        arguments=arguments,
        name=name,
        description=description,
        severity=severity,
        run_scope=run_scope,
        always_run=always_run,
    )


def _optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def _optional_named_bool(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> bool:
    if raw_value is None:
        return False
    if not isinstance(raw_value, bool):
        raise error_class(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value
