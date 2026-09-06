"""Versioned runtime observability catalogs and decision values."""

from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.runtime.observability.models import LifecycleEventDefinition

CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION: int = 1
CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION: int = 1
DURATION_MS_FIELD: str = "duration_ms"
EXIT_CODE_FIELD: str = "exit_code"
PROCESS_ID_FIELD: str = "process_id"
SIGNAL_NUMBER_FIELD: str = "signal_number"
METADATA_FIELD: str = "metadata"
CONFIGURED_CONCURRENCY_FIELD: str = "configured_concurrency"
RUN_STARTED_EVENT: str = "run_started"
RUN_TERMINALS: frozenset[str] = frozenset({"run_completed", "run_failed"})
AUDIT_RUN_COUNT_FIELDS: frozenset[str] = frozenset({"pass_count", "warn_count", "fail_count"})
STATEMENT_EVENT_PREFIX: str = "statement_"
MAX_METADATA_BYTES: int = 4096
DIAGNOSTIC_SEVERITIES: frozenset[str] = frozenset(
    {"trace", "debug", "info", "warning", "error", "critical"}
)
ERROR_FIELDS: frozenset[str] = frozenset({"error_code", "error_type"})
DURATION_FIELDS: frozenset[str] = frozenset({DURATION_MS_FIELD})
RESOURCE_FIELDS: frozenset[str] = frozenset({"resource_kind", "resource_name", "attempt_number"})
RESOURCE_SKIP_CODES: frozenset[str] = frozenset({"dependency", "explicit", "fan_in", "scheduler"})
RESOURCE_SKIP_MODES: frozenset[str] = frozenset({"hard", "soft"})
RESOURCE_ATTEMPT_SKIPPED_EVENT: str = "resource_attempt_skipped"
RESOURCE_TERMINALS: frozenset[str] = frozenset(
    {"resource_attempt_completed", "resource_attempt_failed", RESOURCE_ATTEMPT_SKIPPED_EVENT}
)
HOOK_PHASES: frozenset[str] = frozenset({"post_hooks", "pre_hooks"})
HOOK_TYPES: frozenset[str] = frozenset({"python", "sql"})
OPERATION_FIELDS: frozenset[str] = frozenset(
    {
        "operation_kind",
        "operation_name",
        METADATA_FIELD,
        "hook_phase",
        "hook_index",
        "hook_type",
        "hook_name",
        "phase",
        "strategy",
        "adapter",
        "target_kind",
        "scope",
    }
)
OPERATION_EVENT_PREFIX: str = "operation_"
RENAME_OPERATION_STRATEGY: str = "rename"
RETRY_SCHEDULED_EVENT: str = "retry_scheduled"
STATEMENT_FAILED_EVENT: str = "statement_failed"
STATEMENT_HEARTBEAT_THRESHOLD_SECONDS: float = 30.0
OPERATION_KINDS: frozenset[str] = frozenset(
    {
        "clone",
        "freshness",
        "janitor",
        "loader",
        "project",
        "python_node",
        "quality",
        "scenario",
        "subprocess",
        "warehouse",
    }
)
OPERATION_NAMES: frozenset[str] = frozenset(
    {
        "clone_finalization",
        "clone_execution",
        "clone_namespace_preparation",
        "clone_relation_inspection",
        "clone_relation_transfer",
        "clone_retention_reconciliation",
        "clone_state_connection",
        "clone_state_inspection",
        "clone_target_connection",
        "dbt_command",
        "discovery_declaration_parse",
        "discovery_filesystem_walk",
        "discovery_project_assembly",
        "discovery_python_import",
        "external_manifest_discovery",
        "external_source_load",
        "ingestr_command",
        "janitor_candidate_planning",
        "janitor_cleanup_action",
        "janitor_execution",
        "janitor_state_inspection",
        "janitor_target_connection",
        "janitor_warehouse_inspection",
        "managed_source_load",
        "project_compile",
        "project_discovery",
        "python_asset",
        "python_check",
        "python_hook",
        "python_materialization",
        "python_task",
        "sql_hook",
        "scenario_capture",
        "scenario_cleanup",
        "scenario_execution",
        "scenario_relation_read",
        "scenario_schema_inspection",
        "scenario_snapshot_serialization",
        "scenario_snapshot_write",
        "scenario_target_connection",
        "source_freshness_metadata_observation",
        "source_freshness_query_observation",
        "source_freshness_publication",
        "audit_evaluation",
        "sql_test_setup",
        "sql_test_assertion",
        "retention_inspection",
        "retention_application",
        "table_type_inspection",
        "table_type_conversion",
        "runtime_schema_inspection",
        "schema_synchronization",
        "staging_creation",
        "relation_promotion",
    }
)
OPERATION_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "attempt_number",
        "byte_count",
        "item_count",
        "row_count",
        "changed_count",
        "added_count",
        "removed_count",
        "altered_count",
    }
)
OPERATION_PHASES: frozenset[str] = frozenset(
    {
        "inspect",
        "apply",
        "assert",
        "convert",
        "create",
        "evaluate",
        "observe",
        "promote",
        "publish",
        "reconcile",
        "setup",
    }
)
OPERATION_STRATEGIES: frozenset[str] = frozenset(
    {
        "atomic_replace",
        "atomic_swap",
        RENAME_OPERATION_STRATEGY,
        "build_aside",
        "create_new",
        "virtual",
        "append_new_columns",
        "sync_all_columns",
        "adapter",
        "column",
        "sql",
    }
)
OPERATION_TARGET_KINDS: frozenset[str] = frozenset(
    {
        "audit",
        "namespace",
        "relation",
        "source",
        "sql_test",
        "staging_relation",
        "state_batch",
        "virtual_environment",
    }
)
OPERATION_SCOPES: frozenset[str] = frozenset(
    {"delta", "end", "final", "model", "source", "standalone"}
)
OPERATION_ADAPTERS: frozenset[str] = frozenset(
    {
        "bigquery",
        "custom",
        "databricks",
        "duckdb",
        "motherduck",
        "postgres",
        "snowflake",
        "sqlserver",
    }
)
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
        "hook_name",
        "hook_phase",
        "hook_type",
        "intent",
        "job_id",
        "operation_kind",
        "operation_name",
        "query_id",
        "resource_kind",
        "resource_name",
        "run_kind",
        "scope",
        "sql_digest",
        "statement_kind",
        "audit_name",
        "evaluation_mode",
        "outcome",
        "severity",
        "run_scope_phase",
        "attachment_kind",
        "binding_key",
        "definition_fingerprint",
        "execution_fingerprint",
        "attached_target_kind",
        "attached_target_name",
        "attached_column_name",
        "target_database",
        "target_schema",
        "target_name",
        "sample_unit",
        "evidence_error",
        "measurement_sql",
        "evidence_sql",
        "executed_sql",
        "execution_error",
        "result_id",
    }
)
NONNEGATIVE_INTEGER_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "affected_rows",
        "attempt_number",
        "batch_size",
        "delay_ms",
        "failed_count",
        "fail_count",
        "failed_attempt_number",
        "hook_index",
        "next_attempt_number",
        PROCESS_ID_FIELD,
        "row_count",
        "selected_count",
        "configured_concurrency",
        "pass_count",
        SIGNAL_NUMBER_FIELD,
        "skipped_count",
        "succeeded_count",
        "warn_count",
        "worker_count",
        "violation_count",
        "sample_count",
        "minimum_samples",
        "evidence_count",
    }
)
FINITE_NUMBER_PAYLOAD_FIELDS: frozenset[str] = frozenset({"measured_value"})
BOOLEAN_PAYLOAD_FIELDS: frozenset[str] = frozenset({"evidence_truncated", "reused"})
JSON_PAYLOAD_FIELDS: frozenset[str] = frozenset({"thresholds", "evidence"})
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
            allowed=frozenset(
                {"run_kind", "selected_count", "configured_concurrency", "worker_count"}
            ),
        ),
        "run_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            allowed=frozenset(
                {
                    "run_kind",
                    "succeeded_count",
                    "failed_count",
                    "skipped_count",
                    "pass_count",
                    "warn_count",
                    "fail_count",
                }
            )
            | DURATION_FIELDS,
            terminal=True,
        ),
        "run_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            allowed=frozenset(
                {
                    "run_kind",
                    "succeeded_count",
                    "failed_count",
                    "skipped_count",
                    "pass_count",
                    "warn_count",
                    "fail_count",
                }
            )
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
        RESOURCE_ATTEMPT_SKIPPED_EVENT: LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id", "resource_id", "resource_attempt_id"}),
            required_payload=RESOURCE_FIELDS | frozenset({"skip_code"}),
            allowed=RESOURCE_FIELDS | DURATION_FIELDS | frozenset({"skip_code", "skip_mode"}),
            terminal=True,
        ),
        "operation_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}), allowed=OPERATION_FIELDS
        ),
        "operation_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}),
            allowed=OPERATION_FIELDS
            | DURATION_FIELDS
            | frozenset({EXIT_CODE_FIELD, PROCESS_ID_FIELD, SIGNAL_NUMBER_FIELD}),
            terminal=True,
        ),
        "operation_failed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"operation_id"}),
            allowed=OPERATION_FIELDS
            | DURATION_FIELDS
            | ERROR_FIELDS
            | frozenset({EXIT_CODE_FIELD, PROCESS_ID_FIELD, SIGNAL_NUMBER_FIELD}),
            terminal=True,
        ),
        RETRY_SCHEDULED_EVENT: LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id", "resource_id", "resource_attempt_id"}),
            required_payload=frozenset(
                {
                    "failed_attempt_number",
                    "next_attempt_number",
                    "delay_ms",
                    "error_type",
                }
            ),
            allowed=frozenset(
                {
                    "failed_attempt_number",
                    "next_attempt_number",
                    "delay_ms",
                    "error_type",
                    "error_code",
                }
            ),
        ),
        "audit_completed": LifecycleEventDefinition.create(
            required_correlations=frozenset({"run_id"}),
            required_payload=frozenset(
                {
                    "audit_name",
                    "evaluation_mode",
                    "outcome",
                    "severity",
                    "run_scope_phase",
                    "attachment_kind",
                }
            ),
            allowed=frozenset(
                {
                    "audit_name",
                    "evaluation_mode",
                    "outcome",
                    "severity",
                    "run_scope_phase",
                    "attachment_kind",
                    "binding_key",
                    "definition_fingerprint",
                    "execution_fingerprint",
                    "attached_target_kind",
                    "attached_target_name",
                    "attached_column_name",
                    "target_database",
                    "target_schema",
                    "target_name",
                    "violation_count",
                    "measured_value",
                    "sample_count",
                    "sample_unit",
                    "minimum_samples",
                    "thresholds",
                    "evidence",
                    "evidence_count",
                    "evidence_truncated",
                    "evidence_error",
                    "measurement_sql",
                    "evidence_sql",
                    "executed_sql",
                    "sql_digest",
                    "execution_error",
                    "reused",
                    "result_id",
                }
            ),
            terminal=True,
        ),
        "statement_started": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}), allowed=STATEMENT_FIELDS
        ),
        "statement_submitted": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}),
            allowed=STATEMENT_FIELDS - frozenset({"row_count"}),
        ),
        "statement_heartbeat": LifecycleEventDefinition.create(
            required_correlations=frozenset({"statement_id"}),
            allowed=STATEMENT_FIELDS | DURATION_FIELDS,
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
    {CURRENT_LIFECYCLE_EVENT_SCHEMA_VERSION: LIFECYCLE_EVENT_CATALOG_V1}
)
LIFECYCLE_EVENT_CATALOG: Mapping[str, LifecycleEventDefinition] = LIFECYCLE_EVENT_CATALOG_V1
