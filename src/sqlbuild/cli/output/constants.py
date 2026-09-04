"""CLI execution output constants."""

from sqlbuild.executor.clone.types import CloneAction
from sqlbuild.spec.contracts.types import FutureCursorAction, MicrobatchLimitAction

INTEGRATION_RESULT_PATH_ENV: str = "SQLBUILD_INTEGRATION_RESULT_PATH"
INTEGRATION_RESULT_SCHEMA_VERSION: int = 1
INTEGRATION_RESULT_RECORD_KIND: str = "integration_result"
INTEGRATION_RESOURCE_FAILED_EVENT: str = "resource_attempt_failed"
INTEGRATION_CHECK_PASS_STATUS: str = "pass"
INTEGRATION_FAILED_STATUS: str = "failed"
INTEGRATION_SKIPPED_STATUS: str = "skipped"
INTEGRATION_LOADER_KIND: str = "loader"
MAX_INTEGRATION_RECORD_BYTES: int = 65_536
MAX_INTEGRATION_STRING_CHARS: int = 2_048
MAX_INTEGRATION_IDENTIFIER_CHARS: int = 512
MAX_INTEGRATION_COLLECTION_ITEMS: int = 128
MAX_INTEGRATION_NESTING_DEPTH: int = 6
MAX_INTEGRATION_METADATA_BYTES: int = 16_384
INTEGRATION_ASSET_KINDS: frozenset[str] = frozenset(
    {
        "asset",
        "custom",
        "loader",
        "model",
        "seed",
        "snapshot",
        "source",
        "table",
        "table_fn",
        "task",
        "udf",
        "view",
    }
)
INTEGRATION_CHECK_KINDS: frozenset[str] = frozenset({"audit", "python_check", "sql_test"})
INTEGRATION_RESOURCE_KINDS: frozenset[str] = INTEGRATION_ASSET_KINDS | frozenset(
    {"audit", "check", "test"}
)
INTEGRATION_ASSET_STATUSES: frozenset[str] = frozenset({"failed", "skipped", "success", "warning"})
INTEGRATION_FAILED_PHASES: frozenset[str] = frozenset(
    {
        "audit",
        "contract",
        "custom_materialization",
        "dml",
        "fingerprint",
        "microbatch_state",
        "post_hook",
        "pre_hook",
        "promotion",
        "schema_change",
        "staging",
        "type_enforcement",
    }
)
INTEGRATION_CHECK_STATUSES: frozenset[str] = frozenset({"error", "fail", "pass", "warn"})
INTEGRATION_CHECK_SEVERITIES: frozenset[str] = frozenset({"error", "warn"})
INTEGRATION_CHECK_ATTACHMENT_KINDS: frozenset[str] = frozenset({"end", "model", "source"})
INTEGRATION_CHECK_RUN_SCOPE_PHASES: frozenset[str] = frozenset({"delta_and_final", "final"})
INTEGRATION_CLONE_ACTIONS: frozenset[str] = frozenset(action.value for action in CloneAction)
INTEGRATION_SKIP_MODES: frozenset[str] = frozenset({"hard", "soft"})
INTEGRATION_FUTURE_CURSOR_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "applied_bounds",
        "cursor_column",
        "determining_input",
        "discovered_bounds",
        "end",
        "future_end_detected",
        "future_start_detected",
        "inputs",
        "invocation_time",
        "max_distance",
        "maximum",
        "maximum_allowed_bounds",
        "minimum",
        "relation",
        "start",
    }
)
INTEGRATION_MAXIMUM_START_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "cursor_column",
        "effective_start",
        "highest_eligible_target_max",
        "input",
        "invocation_time",
        "max_ahead",
        "maximum_allowed_start",
        "physical_target_max",
        "relation",
    }
)
INTEGRATION_MAXIMUM_START_ACTIONS: frozenset[str] = frozenset(
    action.value for action in FutureCursorAction
)
INTEGRATION_MAXIMUM_START_INPUT_KEYS: frozenset[str] = frozenset({"relation", "cursor_column"})
INTEGRATION_MAXIMUM_START_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "max_ahead",
        "invocation_time",
        "physical_target_max",
        "highest_eligible_target_max",
        "effective_start",
        "maximum_allowed_start",
        "input",
    }
)
INTEGRATION_MICROBATCH_KEYS: frozenset[str] = frozenset(
    {
        "action",
        "batch_concurrency",
        "batch_count",
        "batch_size",
        "concurrent_enabled",
        "contiguous_frontier",
        "count",
        "global_concurrency",
        "known_gap_count",
        "limit",
        "physical_generation_id",
        "recovery_batch_count",
        "replay_requirement_id",
        "replay_requirement_state",
        "required_model_version_hash",
        "run_type",
        "strategy",
        "reason",
        "synthetic_completion_count",
        "unaccounted_interval_count",
        "unaccounted_partition_policy",
        "unknown_fingerprint_count",
    }
)
INTEGRATION_MICROBATCH_COUNT_KEYS: frozenset[str] = frozenset(
    {
        "batch_concurrency",
        "batch_count",
        "count",
        "global_concurrency",
        "known_gap_count",
        "limit",
        "recovery_batch_count",
        "synthetic_completion_count",
        "unaccounted_interval_count",
        "unknown_fingerprint_count",
    }
)
INTEGRATION_MICROBATCH_RUN_TYPES: frozenset[str] = frozenset(
    {"backfill", "normal", "replay_on_change"}
)
INTEGRATION_MICROBATCH_LIMIT_ACTIONS: frozenset[str] = frozenset(
    action.value for action in MicrobatchLimitAction
)
INTEGRATION_MICROBATCH_PARTITION_POLICIES: frozenset[str] = frozenset(
    {"recover_all", "recover_empty", "synthesize"}
)
INTEGRATION_MICROBATCH_REPLAY_STATES: frozenset[str] = frozenset(
    {"complete_with_unknown_fingerprints", "incomplete", "superseded", "verified_complete"}
)
