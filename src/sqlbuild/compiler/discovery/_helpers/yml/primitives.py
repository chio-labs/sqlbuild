"""Shared YAML audit-list parsing for discovery parsers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.auditing.main._parse_audit_instance import parse_audit_instance
from sqlbuild.spec.contracts.models import SchemaAuditInstance


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
