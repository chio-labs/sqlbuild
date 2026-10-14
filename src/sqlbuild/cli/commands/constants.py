"""CLI command decision constants."""

from types import MappingProxyType

from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.spec.contracts.types import WarehouseGroup

C0_CONTROL_CODE_LIMIT: int = 32
C1_CONTROL_CODE_START: int = 127
C1_CONTROL_CODE_LIMIT: int = 160
EMPTY_DAG_PATH: str = ""
TARGET_DIRECTORY_NAME: str = "target"
SQLBUILD_CONCURRENCY_ENV_VAR: str = "SQLBUILD_CONCURRENCY"
NO_COLOR_OPTION: str = "--no-color"
DBT_INIT_COMMAND: str = "init"
SCENARIO_TEST_COMMAND: str = "test"
SCENARIO_CAPTURE_COMMAND: str = "capture"
JSON_OUTPUT_FORMAT: str = "json"
CSV_OUTPUT_FORMAT: str = "csv"
DEBUG_COMMAND: str = "debug"
LINEAGE_COMMAND: str = "lineage"
QUERY_COMMAND: str = "query"
RULES_LIST_ACTION: str = "list"
RULES_SHOW_ACTION: str = "show"
RULES_SKILLS_ACTION: str = "skills"
SQL_FILE_SUFFIX: str = ".sql"
SUCCESS_STATUS: str = "success"
FAILED_STATUS: str = "failed"
SCENARIO_CLI_MISSING_SUBCOMMAND: str = "C450"
SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
COST_NARROW_TERMINAL_WIDTH: int = 120
COST_HISTORY_NUMERIC_COLUMNS: frozenset[int] = frozenset({4, 5})
COST_RESOURCE_NUMERIC_START_COLUMN: int = 2
BYTE_SCALE: int = 1024
BYTE_UNIT: str = "B"
TERABYTE_UNIT: str = "TiB"
SCOPE_PATH_RELATIVE: str = "relative"
SCOPE_PATH_COMPACT: str = "compact"
SCOPE_PATH_NONE: str = "none"
SCOPE_GLOBAL_SUMMARY: str = "summary"
SCOPE_GLOBAL_ALL: str = "all"
SCOPE_DEFAULT_PAGE_SIZE: int = 100
MISSING_ORIGIN_BUILD_HELP: str = (
    "Pass --allow-missing-migration-origin to confirm in non-interactive runs."
)
MISSING_ORIGIN_DBT_HELP: str = (
    "sqb dbt has no confirmation flag: confirm on an interactive terminal, build the affected "
    "models with sqb build --allow-missing-migration-origin and leave them out of this dbt "
    "selection, or set the target's missing_migration_origin to 'allow'."
)
SNAPSHOT_FULL_REFRESH_BUILD_HELP: str = (
    "Pass --allow-snapshot-full-refresh to confirm in non-interactive runs."
)
SNAPSHOT_FULL_REFRESH_DBT_HELP: str = (
    "sqb dbt has no confirmation flag: confirm on an interactive terminal, build the affected "
    "snapshots with sqb build --allow-snapshot-full-refresh and leave them out of this dbt "
    "selection, or relax the snapshot_full_refresh policy."
)
TABLE_TYPE_DOWNGRADE_BUILD_HELP: str = (
    "Pass --allow-table-type-downgrade to confirm in non-interactive runs."
)
TABLE_TYPE_DOWNGRADE_DBT_HELP: str = (
    "sqb dbt has no confirmation flag: confirm on an interactive terminal, build the affected "
    "models with sqb build --allow-table-type-downgrade and leave them out of this dbt "
    "selection, or set the target's table_type_downgrade to 'allow'."
)
RETENTION_DECREASE_BUILD_HELP: str = (
    "Pass --allow-retention-decrease to confirm in non-interactive runs."
)
RETENTION_DECREASE_DBT_HELP: str = (
    "sqb dbt has no confirmation flag: confirm on an interactive terminal, build the affected "
    "models with sqb build --allow-retention-decrease and leave them out of this dbt "
    "selection, or set the target's time_travel_retention_decrease to 'allow'."
)
EXECUTION_LIMIT_BUILD_NOTE: str = "No warehouse changes were made."
EXECUTION_LIMIT_DBT_NOTE: str = "dbt work has already run; no SQLBuild models were built."
CLI_WAREHOUSE_SOURCE: str = "--warehouse"
CONNECTION_WAREHOUSE_SOURCE: str = "connection warehouse"
CONNECTION_DEFAULT_WAREHOUSE_SOURCE: str = "connection default"
COMMAND_WAREHOUSE_GROUPS: MappingProxyType[CliCommand, WarehouseGroup | None] = MappingProxyType(
    {
        CliCommand.AUDIT: WarehouseGroup.BUILD,
        CliCommand.BUILD: WarehouseGroup.BUILD,
        CliCommand.CHECK: WarehouseGroup.BUILD,
        CliCommand.CLONE: WarehouseGroup.BUILD,
        CliCommand.DBT: WarehouseGroup.BUILD,
        CliCommand.LOAD: WarehouseGroup.BUILD,
        CliCommand.PLAN: WarehouseGroup.BUILD,
        CliCommand.SEED: WarehouseGroup.BUILD,
        CliCommand.CONTRACT: WarehouseGroup.QUERY,
        CliCommand.COST: WarehouseGroup.QUERY,
        CliCommand.DEBUG: WarehouseGroup.QUERY,
        CliCommand.DIFF: WarehouseGroup.QUERY,
        CliCommand.FRESHNESS: WarehouseGroup.QUERY,
        CliCommand.QUERY: WarehouseGroup.QUERY,
        CliCommand.JANITOR: WarehouseGroup.QUERY,
        CliCommand.SCENARIO: WarehouseGroup.QUERY,
        CliCommand.TEST: WarehouseGroup.QUERY,
        CliCommand.CLEAN: None,
        CliCommand.COMPILE: None,
        CliCommand.DAG: None,
        CliCommand.FORMAT: None,
        CliCommand.INIT: None,
        CliCommand.LINEAGE: None,
        CliCommand.MV: None,
        CliCommand.PLAYGROUND: None,
        CliCommand.RENAME: None,
        CliCommand.RULES: None,
        CliCommand.SCOPE: None,
        CliCommand.SKILLS: None,
    }
)
