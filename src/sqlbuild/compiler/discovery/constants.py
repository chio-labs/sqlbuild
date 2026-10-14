"""Public discovery constants."""

from __future__ import annotations

PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.toml"
LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.toml"
LEGACY_PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.yml"
LEGACY_LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.yml"
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

DLT_SOURCE_TYPE_SQL_DATABASE: str = "sql_database"
DLT_SOURCE_TYPE_REST_API: str = "rest_api"
DLT_SOURCE_TYPE_FILESYSTEM: str = "filesystem"

SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
SQL_TEST_HEADER_KEYS: frozenset[str] = frozenset(
    {"name", "mode", "parameters", "cases", "cursor_start", "cursor_end", SQL_ANALYSIS_CONFIG_KEY}
)
SQL_SCENARIO_HEADER_KEYS: frozenset[str] = frozenset({"description", "tags"})
SQL_ANALYSIS_SETTING_KEY: str = "sql_analysis"
SETTINGS_SECTION: str = "settings"
QUERY_CHANGE_TRACKING_SETTING_KEY: str = "query_change_tracking"
REFERENCES_SECTION: str = "references"
TABLE_PROMOTION_MODE_SETTING_KEY: str = "table_promotion_mode"
STAGED_PROMOTION_MODE: str = "staged"
DBT_SECTION: str = "dbt"
DEFAULTS_SECTION: str = "defaults"
DBT_PROJECT_DIR_KEY: str = "project_dir"

MODELS_DIRECTORY_NAME: str = "models"
SQL_TESTS_OWNERSHIP_ROOT: str = "tests/unit"
SQL_SCENARIOS_OWNERSHIP_ROOT: str = "tests/scenarios"

CANONICAL_AUTHORED_ROOTS: tuple[tuple[str, ...], ...] = (
    ("models",),
    ("tests", "unit"),
    ("tests", "scenarios"),
    ("functions", "sql"),
    ("sources",),
)

NOT_NULL_AUDIT_NAME: str = "not_null"

SQL_HOOK_OUTPUT_FIELDS: tuple[str, ...] = (
    "statement",
    "name",
    "relative_path",
    "definition_sql",
    "kwargs",
    "description",
)
SQL_HOOK_IDENTITY_FIELDS: tuple[str, ...] = ("statement", "name", "definition_sql", "kwargs")
