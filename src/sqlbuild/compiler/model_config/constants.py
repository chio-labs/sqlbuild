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
UNSUPPORTED_OUTCOME: str = "unsupported"
ENVIRONMENT_READ: str = "env"
COLUMNS_HEADER_KEY: str = "columns"
AUDITS_HEADER_KEY: str = "audits"
CONFIG_VALUE_TYPE_ERROR: str = "config_value_type"
RESOURCE_IDENTITY_ERROR: str = "resource_identity"
DISCOVERY_CONFLICT_ERROR: str = "discovery_conflict"
EXPECTED_STRING: str = "a string"
