"""dbt integration constants."""

from sqlbuild.integrations.dbt.types import DbtInteropCommand

DBT_EXECUTION_COMMANDS: frozenset[DbtInteropCommand] = frozenset(
    (
        DbtInteropCommand.PLAN,
        DbtInteropCommand.RUN,
        DbtInteropCommand.BUILD,
        DbtInteropCommand.TEST,
    )
)
DBT_EXECUTION_DISPLAY_FLAGS: frozenset[str] = frozenset(("--json", "--verbose", "-v"))

DBT_MANIFEST_CONFIG_KEY: str = "config"
DBT_MANIFEST_INCREMENTAL_STRATEGY_KEY: str = "incremental_strategy"
DBT_MANIFEST_MATERIALIZED_KEY: str = "materialized"
DBT_MANIFEST_META_KEY: str = "meta"
DBT_MANIFEST_RESOURCE_TYPE_KEY: str = "resource_type"
DBT_MANIFEST_SQLBUILD_META_KEY: str = "sqlbuild"

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
