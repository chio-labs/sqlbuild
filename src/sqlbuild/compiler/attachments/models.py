"""Plain values exchanged with the native compile attachments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NativeAuditPolicies:
    """One attachment's evaluation mode, threshold facts, severities and run scopes."""

    measurement: bool
    has_thresholds: bool
    has_minimum_samples: bool
    threshold_error: bool
    instance_severity: str | None
    default_severity: str | None
    instance_run_scope: str | None
    default_run_scope: str | None


@dataclass(frozen=True, slots=True)
class NativeRenderedAudit:
    """Rendered audit SQL, the severity value and where the run scope comes from."""

    sql_body: str
    evidence_sql: str | None
    severity: str
    run_scope_source: str


@dataclass(frozen=True, slots=True)
class NativeNamedType:
    """One function argument or return column: authored name, stripped name, stripped type."""

    raw_name: str
    name: str
    type_text: str


@dataclass(frozen=True, slots=True)
class NativeFunctionHeader:
    """A function header Python accepts, with argument and return types still unexpanded."""

    arguments: tuple[NativeNamedType, ...]
    returns: str | None
    return_columns: tuple[NativeNamedType, ...] | None
    tags: tuple[str, ...]
    description: str | None
    runtime_version: str | None
    entry_point: str | None
    packages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NativeFunctionNamespaceInputs:
    """Expanded header, project default and target namespaces of one function."""

    header_database: str | None
    header_schema: str | None
    default_database: str | None
    default_schema: str | None
    target_database: str | None
    target_schema: str | None
    python: bool
    inherit_default_namespace: bool


@dataclass(frozen=True, slots=True)
class NativeFunctionNamespace:
    """Physical, logical and fingerprint database and schema of one function."""

    database: str | None
    schema: str | None
    logical_database: str | None
    logical_schema: str | None
    fingerprint_database: str | None
    fingerprint_schema: str | None
    fingerprint_logical_database: str | None
    fingerprint_logical_schema: str | None
