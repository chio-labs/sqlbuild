"""Dagster integration protocol constants."""

from __future__ import annotations

DAGSTER_ASSET_NODE_KINDS: frozenset[str] = frozenset(
    {"source", "loader", "seed", "model", "udf", "table_fn", "task", "asset"}
)
DAGSTER_DIRECT_KIND_NODE_KINDS: frozenset[str] = frozenset(
    {"source", "loader", "seed", "task", "asset", "udf", "table_fn"}
)
MODEL_NODE_KIND: str = "model"
SOURCE_NODE_KIND: str = "source"
LOADER_NODE_KIND: str = "loader"
VIEW_MATERIALIZATION_TYPE: str = "view"

ASSET_SELECTION_COMMANDS: frozenset[str] = frozenset(
    {"build", "run", "test", "check", "audit", "seed", "load", "clone"}
)
CLONE_COMMAND: str = "clone"
CHECK_COMMAND: str = "check"
EVENT_OUTPUT_FLAG: str = "--event-output"
LIVE_EVENT_COMMANDS: frozenset[str] = ASSET_SELECTION_COMMANDS
VIRTUAL_ENV_FLAG: str = "--virtual-env"
VERBOSE_FLAGS: frozenset[str] = frozenset({"--verbose", "-v"})
EXPLICIT_SELECTION_FLAGS: frozenset[str] = frozenset({"--select", "-s", "--select-file"})
JSON_OUTPUT_FLAGS: frozenset[str] = frozenset({"--json", "--json-output"})
JSON_OUTPUT_FLAG: str = "--json-output"
SELECT_FILE_FLAG: str = "--select-file"
SCENARIO_TEST_COMMAND: tuple[str, str] = ("scenario", "test")
SCENARIO_CHECK_KIND: str = "scenario"
SCENARIO_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--max-snapshot-rows",
        "--max-snapshot-total-rows",
        "--max-snapshot-bytes",
        "--max-snapshot-total-bytes",
    }
)
LOAD_COMMAND: str = "load"
LOAD_SELECTABLE_NODE_KINDS: frozenset[str] = frozenset({"source", "loader"})
DEFAULT_SELECTABLE_NODE_KINDS: frozenset[str] = frozenset(
    {"source", "seed", "model", "udf", "table_fn"}
)
MATERIALIZABLE_NODE_KINDS: frozenset[str] = frozenset(
    {"source", "loader", "seed", "model", "udf", "table_fn"}
)
COMPLETED_EXECUTION_STATUSES: frozenset[str] = frozenset({"success", "skipped"})
SUCCESS_EXECUTION_STATUS: str = "success"
FAILED_EXECUTION_STATUS: str = "failed"
CHECK_NAME_SEPARATOR_CHARACTER: str = "_"
CHECK_METADATA_EXCLUDED_KEYS: frozenset[str] = frozenset(
    {"passed", "steps", "expected_results", "assertion_results"}
)
WARNING_CHECK_SEVERITY: str = "warn"
STDERR_STREAM_NAME: str = "stderr"
