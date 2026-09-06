"""Schema-attached audit parsing entrypoint."""

from pathlib import Path

from sqlbuild.compiler.auditing._helpers.schema_audits import (
    parse_audit_instance_impl,
    parse_measurement_thresholds,  # noqa: F401 - sibling-domain role export
    parse_minimum_samples,  # noqa: F401 - sibling-domain role export
)
from sqlbuild.spec.contracts.models import SchemaAuditInstance


def parse_audit_instance(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> SchemaAuditInstance:
    """Parse one audit instance from a raw mapping or string value."""

    return parse_audit_instance_impl(
        raw_audit=raw_audit,
        file_path=file_path,
        label=label,
        error_class=error_class,
    )
