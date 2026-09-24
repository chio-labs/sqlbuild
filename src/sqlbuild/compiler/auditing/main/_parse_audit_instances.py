"""Schema-attached audit list parsing entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.auditing._helpers.schema_audits import parse_audit_instances_impl
from sqlbuild.spec.contracts.models import SchemaAuditInstance


def parse_audit_instances(
    *,
    raw_audits: object | None,
    file_path: Path,
    label: str,
    error_class: type[Exception],
    null_as_empty: bool,
) -> tuple[SchemaAuditInstance, ...]:
    """Parse an authored audit list, treating null as empty only when requested."""

    return parse_audit_instances_impl(
        raw_audits=raw_audits,
        file_path=file_path,
        label=label,
        error_class=error_class,
        null_as_empty=null_as_empty,
    )
