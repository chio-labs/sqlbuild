"""Schema-attached audit parsing implementation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.constants import SCHEMA_AUDIT_OPTION_KEYS
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.spec.contracts.models import SchemaAuditInstance


def parse_audit_instance_impl(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> SchemaAuditInstance:
    """Parse one audit instance from a raw mapping or string value."""

    if isinstance(raw_audit, str):
        if not raw_audit.strip():
            raise error_class(f"{file_path} {label} audits must not contain empty names")
        validate_resource_identity(
            name=raw_audit,
            kind=f"{label} audit definition",
            path=file_path,
        )
        return SchemaAuditInstance(definition_name=raw_audit)

    if not isinstance(raw_audit, dict) or len(raw_audit) != 1:
        raise error_class(f"{file_path} {label} audits must be strings or single-key mappings")

    typed_audit_mapping: dict[str, object] = cast(dict[str, object], raw_audit)
    definition_name: str = next(iter(typed_audit_mapping))
    if not isinstance(definition_name, str) or not definition_name.strip():
        raise error_class(f"{file_path} {label} audit names must be non-empty strings")
    validate_resource_identity(
        name=definition_name,
        kind=f"{label} audit definition",
        path=file_path,
    )

    raw_arguments: object = typed_audit_mapping[definition_name]
    if raw_arguments is None:
        return SchemaAuditInstance(definition_name=definition_name)
    if not isinstance(raw_arguments, dict):
        raise error_class(
            f"{file_path} {label} audit '{definition_name}' arguments must be a mapping"
        )

    argument_mapping: dict[str, object] = cast(dict[str, object], raw_arguments)
    option_label: str = f"{label} audit '{definition_name}'"
    name: str | None = _optional_named_string(
        raw_value=argument_mapping.get("name"),
        file_path=file_path,
        label=option_label,
        key="name",
        error_class=error_class,
    )
    if name is not None:
        validate_resource_identity(
            name=name,
            kind=f"{label} audit instance",
            path=file_path,
        )
    description: str | None = _optional_named_string(
        raw_value=argument_mapping.get("description"),
        file_path=file_path,
        label=option_label,
        key="description",
        error_class=error_class,
    )
    severity: str | None = _optional_named_string(
        raw_value=argument_mapping.get("severity"),
        file_path=file_path,
        label=option_label,
        key="severity",
        error_class=error_class,
    )
    run_scope: str | None = _optional_named_string(
        raw_value=argument_mapping.get("run_scope"),
        file_path=file_path,
        label=option_label,
        key="run_scope",
        error_class=error_class,
    )
    always_run: bool = _optional_named_bool(
        raw_value=argument_mapping.get("always_run"),
        file_path=file_path,
        label=option_label,
        key="always_run",
        error_class=error_class,
    )
    arguments: dict[str, object] = {
        key: value for key, value in argument_mapping.items() if key not in SCHEMA_AUDIT_OPTION_KEYS
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
