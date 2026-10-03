"""Public discovery constants."""

from __future__ import annotations

PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.toml"
LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.toml"
LEGACY_PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.yml"
LEGACY_LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.yml"
TOML_FILE_SUFFIX: str = ".toml"
SCHEMA_FILE_NAME: str = "schema.yml"
SEED_FILE_SUFFIX: str = ".csv"
YAML_FILE_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})
RESERVED_MODEL_NAMES: frozenset[str] = frozenset({"_chain_"})

PYTHON_INIT_MODULE_STEM: str = "__init__"
PYTHON_CACHE_DIRECTORY_NAME: str = "__pycache__"
LANGUAGE_PYTHON_ROOT_PART_COUNT: int = 2
PYTHON_NODE_ROOT: str = "python"
PYTHON_UDF_DECORATOR_NAME: str = "udf"
SQL_FUNCTION_HEADER_KEYS: frozenset[str] = frozenset(
    {"arguments", "returns", "database", "schema", "tags", "description"}
)
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
PYTHON_UDF_KEYS: frozenset[str] = frozenset(
    {
        "description",
        "arguments",
        "returns",
        "runtime_version",
        "entry_point",
        "packages",
        "database",
        "schema",
        "tags",
    }
)
PYTHON_UDF_IMPORT_MODULES: frozenset[str] = frozenset({"sqlbuild", "sqlbuild.functions"})

DLT_LOADER_KIND: str = "dlt"
DLT_SOURCE_TYPE_SQL_DATABASE: str = "sql_database"
DLT_SOURCE_TYPE_REST_API: str = "rest_api"
DLT_SOURCE_TYPE_FILESYSTEM: str = "filesystem"
DLT_SOURCE_TYPES: frozenset[str] = frozenset(
    {DLT_SOURCE_TYPE_SQL_DATABASE, DLT_SOURCE_TYPE_REST_API, DLT_SOURCE_TYPE_FILESYSTEM}
)
DLT_RESOURCE_WRITE_STRATEGY_KEY: str = "write_strategy"
DLT_WRITE_DISPOSITION_DELETE_INSERT: str = "delete_insert"
DLT_WRITE_DISPOSITION_MERGE: str = "merge"

CONFIG_CONCURRENCY_KEY: str = "concurrency"
LEGACY_CONFIG_CONCURRENCY_KEY: str = "max_concurrency"
SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
LEGACY_SQL_VALIDATION_CONFIG_KEY: str = "sql_validation"
SQL_ANALYSIS_SETTING_KEY: str = "sql_analysis"
REQUIRE_SQL_ANALYSIS_SETTING_KEY: str = "require_sql_analysis"
SETTINGS_SECTION: str = "settings"
QUERY_CHANGE_TRACKING_SETTING_KEY: str = "query_change_tracking"
MICROBATCH_CONCURRENCY_SETTING_KEY: str = "microbatch_concurrency"
REFERENCES_SECTION: str = "references"
TABLE_PROMOTION_MODE_SETTING_KEY: str = "table_promotion_mode"
STAGED_PROMOTION_MODE: str = "staged"
DBT_SECTION: str = "dbt"
DEFAULTS_SECTION: str = "defaults"
DBT_PROJECT_DIR_KEY: str = "project_dir"
ENFORCE_EXPLICIT_REFERENCES_KEY: str = "enforce_explicit"
DBT_LEGACY_REUSE_FROM_CONFIG_KEY: str = "reuse_from"
DBT_PRODUCTION_REF_CONFIG_KEY: str = "production_ref"
DBT_DEFER_CLONE_CONFIG_KEY: str = "defer_clone_from"
DBT_REPLAY_ON_CHANGE_CONFIG_KEY: str = "replay_on_change"
SOURCE_LOADER_CONFIG_KEY: str = "loader"
SOURCE_AGE_POLICY_CONFIG_KEY: str = "age_policy"

MODELS_DIRECTORY_NAME: str = "models"
MODEL_SCHEMAS_DIRECTORY_NAME: str = "schemas"
SEEDS_DIRECTORY_NAME: str = "seeds"
CURRENT_DIRECTORY_PATH: str = "."
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

STATEMENT_HEADER_BODY_PATTERN: str = (
    r"(?P<header>(?>(?:[^\"')\\]|\\.)++"
    r"|\"(?:[^\"\\]|\\.)*+\""
    r"|'(?:[^'\\]|\\.)*+'"
    r"|[\"'](?:[^\\)]|\\.)*+"
    r"|\)(?!\s*;))*+)"
)

DISCOVERY_FACT_CACHE_NAMESPACE: str = "discovery"
DISCOVERY_FACT_CACHE_ALGORITHM: str = "discovered-files-v1"
DISCOVERY_SOURCE_FACT_KIND: str = "source"
DISCOVERY_SQL_TEST_FACT_KIND: str = "sql_test"
