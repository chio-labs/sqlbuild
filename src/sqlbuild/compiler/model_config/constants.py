"""Contract dataclass shapes the native header metadata parser builds."""

from __future__ import annotations

SCHEMA_COLUMN_FIELDS: tuple[str, ...] = (
    "name",
    "type",
    "nullable",
    "description",
    "meta",
    "audits",
    "location",
    "migrate_from",
)
SCHEMA_AUDIT_INSTANCE_FIELDS: tuple[str, ...] = (
    "definition_name",
    "arguments",
    "name",
    "description",
    "severity",
    "run_scope",
    "always_run",
    "thresholds",
    "minimum_samples",
    "evidence_limit",
    "location",
)
INVALID_OUTCOME: str = "invalid"
UNSUPPORTED_OUTCOME: str = "unsupported"
ENVIRONMENT_READ: str = "env"
COLUMNS_HEADER_KEY: str = "columns"
AUDITS_HEADER_KEY: str = "audits"
NATIVE_TEMPLATE_REJECTION_LENGTH: int = 3
