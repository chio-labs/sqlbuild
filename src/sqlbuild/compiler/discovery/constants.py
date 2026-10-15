"""Public discovery constants."""

from __future__ import annotations

PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.toml"
LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.toml"
YAML_FILE_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})

PYTHON_INIT_MODULE_STEM: str = "__init__"
PYTHON_NODE_ROOT: str = "python"
SQL_FUNCTION_HEADER_KEYS: frozenset[str] = frozenset(
    {"arguments", "returns", "database", "schema", "tags", "description"}
)
SQL_AUDIT_HEADER_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "severity",
        "run_scope",
        "always_run",
        "evaluation",
        "value",
        "sample_count",
        "sample_unit",
        "thresholds",
        "minimum_samples",
        "sql_analysis",
    }
)
SQL_HOOK_HEADER_KEYS: frozenset[str] = frozenset({"description"})
SQL_MODEL_HEADER_KEYS: frozenset[str] = frozenset(
    {
        "alias",
        "append_cursor_inclusive",
        "audit_factories",
        "audits",
        "batch_concurrency",
        "batch_size",
        "check_columns",
        "columns",
        "config",
        "constants",
        "contract",
        "cursor",
        "cursor_end",
        "cursor_future_action",
        "cursor_future_max_distance",
        "cursor_grain",
        "cursor_inputs",
        "cursor_start",
        "cursor_start_max_action",
        "cursor_start_max_ahead",
        "cursor_type",
        "cursor_watermark_mode",
        "database",
        "description",
        "dynamic_columns",
        "enabled",
        "enums",
        "full_refresh",
        "historical_input",
        "incremental_mode",
        "incremental_strategy",
        "initial_valid_from",
        "invalidate_hard_deletes",
        "lookback",
        "materialized",
        "max_microbatches",
        "merge_exclude_columns",
        "microbatch_limit",
        "microbatch_strategy",
        "migrate_force",
        "migrate_from",
        "model_schema",
        "observed_at",
        "old_name_view",
        "on_schema_change",
        "placeholders",
        "post_hooks",
        "pre_hooks",
        "replay_on_change",
        "row_diff_exclude_columns",
        "row_diff_sample_rows",
        "row_diff_sample_seed",
        "row_diff_tolerances",
        "schema",
        "snapshot_full_refresh",
        "snapshot_schema_change",
        "snapshot_strategy",
        "sql_analysis",
        "sql_validation",
        "table_type",
        "tags",
        "time_travel_retention",
        "unaccounted_partition_policy",
        "unique_key",
        "updated_at",
        "valid_from_column",
        "valid_to_column",
    }
)
REMOVED_SQL_MODEL_HEADER_KEYS: frozenset[str] = frozenset({"run_despite_unchanged"})


SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
SQL_TEST_HEADER_KEYS: frozenset[str] = frozenset(
    {"name", "mode", "parameters", "cases", "cursor_start", "cursor_end", SQL_ANALYSIS_CONFIG_KEY}
)
SQL_SCENARIO_HEADER_KEYS: frozenset[str] = frozenset({"description", "tags"})
SQL_ANALYSIS_SETTING_KEY: str = "sql_analysis"
SETTINGS_SECTION: str = "settings"
TABLE_PROMOTION_MODE_SETTING_KEY: str = "table_promotion_mode"
STAGED_PROMOTION_MODE: str = "staged"

SQL_TESTS_OWNERSHIP_ROOT: str = "tests/unit"
SQL_SCENARIOS_OWNERSHIP_ROOT: str = "tests/scenarios"


SQL_HOOK_OUTPUT_FIELDS: tuple[str, ...] = (
    "statement",
    "name",
    "relative_path",
    "definition_sql",
    "kwargs",
    "description",
)
