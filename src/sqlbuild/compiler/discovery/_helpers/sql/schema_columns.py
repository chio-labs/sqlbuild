"""Shared parsing for authored model column declarations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.main._parse_audit_instance import parse_audit_instance
from sqlbuild.compiler.compile.constants import NOT_NULL_AUDIT_NAME
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn, SourceLocation

type _SchemaColumnParseError = type[CompileInputError] | type[DeclarationParseError]


def parse_schema_columns(
    *,
    raw_columns: object | None,
    file_path: Path,
    label: str,
    error_class: _SchemaColumnParseError,
    column_locations: dict[str, SourceLocation] | None = None,
    require_columns: bool = False,
) -> tuple[SchemaColumn, ...]:
    """Parse one MODEL or SCHEMA columns mapping into shared contract columns."""

    if raw_columns is None:
        if require_columns:
            raise error_class(f"{file_path} {label} must declare at least one column")
        return ()
    if not isinstance(raw_columns, dict):
        raise error_class(f"{file_path} {label} 'columns' must be a mapping")
    if require_columns and not raw_columns:
        raise error_class(f"{file_path} {label} must declare at least one column")

    locations: dict[str, SourceLocation] = column_locations or {}
    parsed_columns: list[SchemaColumn] = []
    seen_names: set[str] = set()
    column_mapping: dict[object, object] = cast(dict[object, object], raw_columns)
    raw_column_name: object
    raw_column_metadata: object
    for raw_column_name, raw_column_metadata in column_mapping.items():
        if not isinstance(raw_column_name, str) or not raw_column_name.strip():
            raise error_class(f"{file_path} {label} column names must be non-empty strings")
        normalized_name: str = raw_column_name.lower()
        if normalized_name in seen_names:
            raise error_class(
                f"{file_path} {label} has duplicate column '{raw_column_name}' "
                "(column names are case-insensitive)"
            )
        seen_names.add(normalized_name)
        if not isinstance(raw_column_metadata, dict):
            raise error_class(
                f"{file_path} {label} column '{raw_column_name}' metadata must be a mapping"
            )
        column_metadata: dict[str, object] = cast(dict[str, object], raw_column_metadata)
        unknown_keys: set[str] = set(column_metadata) - {
            "type",
            "nullable",
            "description",
            "audits",
        }
        if unknown_keys:
            raise error_class(
                f"{file_path} {label} column '{raw_column_name}' has unknown metadata keys: "
                f"{', '.join(sorted(unknown_keys))}"
            )
        nullable: bool | None = _optional_bool(
            raw_value=column_metadata.get("nullable"),
            file_path=file_path,
            label=f"{label} column '{raw_column_name}'",
            key="nullable",
            error_class=error_class,
        )
        column_location: SourceLocation | None = locations.get(raw_column_name)
        audits: tuple[SchemaAuditInstance, ...] = tuple(
            replace(audit, location=column_location)
            for audit in _parse_audits(
                raw_audits=column_metadata.get("audits"),
                file_path=file_path,
                label=f"{label} column '{raw_column_name}'",
                error_class=error_class,
            )
        )
        if nullable is True and any(
            audit.definition_name == NOT_NULL_AUDIT_NAME for audit in audits
        ):
            message: str = (
                f"{file_path} column '{raw_column_name}' cannot set nullable = true "
                "and audit not_null"
            )
            if error_class is CompileInputError:
                raise error_class(
                    message,
                    code="P002",
                    help="remove the not_null audit or set nullable = false",
                )
            raise error_class(message)
        parsed_columns.append(
            SchemaColumn(
                name=raw_column_name,
                type=_optional_string(
                    raw_value=column_metadata.get("type"),
                    file_path=file_path,
                    label=f"{label} column '{raw_column_name}'",
                    key="type",
                    error_class=error_class,
                ),
                nullable=nullable,
                description=_optional_string(
                    raw_value=column_metadata.get("description"),
                    file_path=file_path,
                    label=f"{label} column '{raw_column_name}'",
                    key="description",
                    error_class=error_class,
                ),
                audits=audits,
                location=column_location,
            )
        )
    return tuple(parsed_columns)


def _parse_audits(
    *, raw_audits: object | None, file_path: Path, label: str, error_class: _SchemaColumnParseError
) -> tuple[SchemaAuditInstance, ...]:
    if raw_audits is None:
        return ()
    if not isinstance(raw_audits, list):
        raise error_class(f"{file_path} {label} audits must be a list")
    return tuple(
        parse_audit_instance(
            raw_audit=raw_audit,
            file_path=file_path,
            label=label,
            error_class=error_class,
        )
        for raw_audit in raw_audits
    )


def _optional_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: _SchemaColumnParseError,
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def _optional_bool(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: _SchemaColumnParseError,
) -> bool | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, bool):
        raise error_class(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value
