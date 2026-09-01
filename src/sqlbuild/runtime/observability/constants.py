"""Versioned runtime observability catalogs and decision values."""

from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.runtime.observability.models import LifecycleEventDefinition

DURATION_MS_FIELD: str = "duration_ms"
EXIT_CODE_FIELD: str = "exit_code"
METADATA_FIELD: str = "metadata"
STATEMENT_EVENT_PREFIX: str = "statement_"
MAX_METADATA_BYTES: int = 4096
DIAGNOSTIC_SEVERITIES: frozenset[str] = frozenset(
    {"trace", "debug", "info", "warning", "error", "critical"}
)
ERROR_FIELDS: frozenset[str] = frozenset({"error_code", "error_type"})
DURATION_FIELDS: frozenset[str] = frozenset({DURATION_MS_FIELD})
RESOURCE_FIELDS: frozenset[str] = frozenset({"resource_kind", "resource_name", "attempt_number"})
OPERATION_FIELDS: frozenset[str] = frozenset({"operation_kind", "operation_name"})
STATEMENT_FIELDS: frozenset[str] = frozenset(
    {
        "adapter",
        "affected_rows",
        "batch_size",
        "intent",
        "job_id",
        METADATA_FIELD,
        "query_id",
        "row_count",
        "sql_digest",
        "statement_kind",
    }
)
STRING_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "adapter",
        "command",
        "error_code",
        "error_type",
        "intent",
        "job_id",
        "operation_kind",
        "operation_name",
        "query_id",
        "resource_kind",
        "resource_name",
        "run_kind",
        "sql_digest",
        "statement_kind",
    }
)
NONNEGATIVE_INTEGER_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "affected_rows",
        "attempt_number",
        "batch_size",
        "failed_count",
        "row_count",
        "selected_count",
        "skipped_count",
        "succeeded_count",
    }
)
FORBIDDEN_STATEMENT_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "bindings",
        "full_sql",
        "parameter_values",
        "parameters",
        "params",
        "query_sql",
        "sql",
        "statement_sql",
    }
)
LIFECYCLE_ENVELOPE_FIELDS: frozenset[str] = frozenset(
    {
        "event_id",
        "event_type",
        "schema_version",
        "producer",
        "producer_version",
        "occurred_at",
        "invocation_id",
        "run_id",
        "resource_id",
        "resource_attempt_id",
        "operation_id",
        "statement_id",
        "payload",
    }
)
DIAGNOSTIC_ENVELOPE_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "producer",
        "producer_version",
        "occurred_at",
        "severity",
        "logger",
        "source",
        "message",
        "fields",
        "log_stream_id",
        "invocation_id",
        "run_id",
        "resource_id",
        "resource_attempt_id",
        "operation_id",
        "statement_id",
    }
)
LIFECYCLE_EVENT_CATALOG_V1: Mapping[str, LifecycleEventDefinition] = MappingProxyType(
    {
        "invocation_started": LifecycleEventDefinition.create(allowed=frozenset({"command"})),
        "invocation_completed": LifecycleEventDefinition.create(
            allowed=frozenset({"command", EXIT_CODE_FIELD}) | DURATION_FIELDS, terminal=True
        ),
        "invocation_failed": LifecycleEventDefinition.create(
            allowed=frozenset({"command", EXIT_CODE_FIELD}) | DURATION_FIELDS | ERROR_FIELDS,
            terminal=True,
        ),
        "run_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            allowed=frozenset({"run_kind", "selected_count"}),
        ),
        "run_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            allowed=frozenset({"run_kind", "succeeded_count", "failed_count", "skipped_count"})
            | DURATION_FIELDS,
            terminal=True,
        ),
        "run_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            allowed=frozenset({"run_kind", "succeeded_count", "failed_count", "skipped_count"})
            | DURATION_FIELDS
            | ERROR_FIELDS,
            terminal=True,
        ),
        "resource_attempt_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id", "resource_id", "resource_attempt_id"}),
            allowed=RESOURCE_FIELDS,
        ),
        "resource_attempt_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id", "resource_id", "resource_attempt_id"}),
            allowed=RESOURCE_FIELDS | DURATION_FIELDS,
            terminal=True,
        ),
        "resource_attempt_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id", "resource_id", "resource_attempt_id"}),
            allowed=RESOURCE_FIELDS | DURATION_FIELDS | ERROR_FIELDS,
            terminal=True,
        ),
        "operation_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}), allowed=OPERATION_FIELDS
        ),
        "operation_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}),
            allowed=OPERATION_FIELDS | DURATION_FIELDS,
            terminal=True,
        ),
        "operation_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}),
            allowed=OPERATION_FIELDS | DURATION_FIELDS | ERROR_FIELDS,
            terminal=True,
        ),
        "statement_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}), allowed=STATEMENT_FIELDS
        ),
        "statement_submitted": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}),
            allowed=STATEMENT_FIELDS - frozenset({"row_count"}),
        ),
        "statement_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}),
            allowed=STATEMENT_FIELDS | DURATION_FIELDS,
            terminal=True,
        ),
        "statement_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}),
            allowed=STATEMENT_FIELDS | DURATION_FIELDS | ERROR_FIELDS,
            terminal=True,
        ),
    }
)
LIFECYCLE_EVENT_CATALOGS: Mapping[int, Mapping[str, LifecycleEventDefinition]] = MappingProxyType(
    {1: LIFECYCLE_EVENT_CATALOG_V1}
)
LIFECYCLE_EVENT_CATALOG: Mapping[str, LifecycleEventDefinition] = LIFECYCLE_EVENT_CATALOG_V1
