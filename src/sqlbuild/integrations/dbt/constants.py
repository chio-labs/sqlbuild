"""dbt integration constants."""

DBT_MANIFEST_CONFIG_KEY: str = "config"
DBT_MANIFEST_INCREMENTAL_STRATEGY_KEY: str = "incremental_strategy"
DBT_MANIFEST_MATERIALIZED_KEY: str = "materialized"
DBT_MANIFEST_META_KEY: str = "meta"
DBT_MANIFEST_RESOURCE_TYPE_KEY: str = "resource_type"
DBT_RESOURCE_TYPE_SNAPSHOT: str = "snapshot"
DBT_MANIFEST_SQLBUILD_META_KEY: str = "sqlbuild"
DBT_MANIFEST_REUSE_CURSOR_KEY: str = "reuse_cursor"

DBT_EXECUTABLE_ENV_VAR: str = "DBT_EXECUTABLE"
DEFAULT_DBT_EXECUTABLE: str = "dbt"

DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "database",
        "alias",
        "target_schema",
        "target_database",
        "tags",
        "docs",
        "group",
        "enabled",
        "packages",
    }
)

DBT_MATERIALIZATION_EPHEMERAL: str = "ephemeral"
DBT_MATERIALIZATION_INCREMENTAL: str = "incremental"
DBT_MATERIALIZATION_MICROBATCH: str = "microbatch"
DBT_MATERIALIZATION_SNAPSHOT: str = "snapshot"
DBT_MATERIALIZATION_TABLE: str = "table"
DBT_MATERIALIZATION_VIEW: str = "view"

DBT_REUSE_METADATA_DBT_TARGET_NAME_KEY: str = "dbt_target_name"
DBT_REUSE_METADATA_DESTINATION_RELATION_KEY: str = "destination_relation"
DBT_REUSE_METADATA_EXECUTION_MODE_KEY: str = "execution_mode"
DBT_REUSE_METADATA_MATERIALIZATION_KEY: str = "materialization"
DBT_REUSE_METADATA_ORIGIN_RELATION_KEY: str = "origin_relation"
DBT_REUSE_METADATA_REUSE_MODE_KEY: str = "reuse_mode"
DBT_REUSE_METADATA_STATUS_KEY: str = "status"
DBT_REUSE_METADATA_CURSOR_COLUMN_KEY: str = "cursor_column"
