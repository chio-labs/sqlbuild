"""CLI command decision constants."""

from types import MappingProxyType

from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.spec.contracts.types import WarehouseGroup

EMPTY_DAG_PATH: str = ""
TARGET_DIRECTORY_NAME: str = "target"
SQLBUILD_CONCURRENCY_ENV_VAR: str = "SQLBUILD_CONCURRENCY"
SQL_ANALYSIS_CONFIG_KEY: str = "sql_analysis"
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
