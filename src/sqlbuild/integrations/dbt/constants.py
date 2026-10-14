"""dbt integration constants."""

from sqlbuild.integrations.dbt.types import DbtInteropCommand

DBT_EXECUTION_COMMANDS: frozenset[DbtInteropCommand] = frozenset(
    (
        DbtInteropCommand.PLAN,
        DbtInteropCommand.RUN,
        DbtInteropCommand.BUILD,
    )
)
DBT_EXECUTION_DISPLAY_FLAGS: frozenset[str] = frozenset(("--json", "--verbose", "-v"))

DBT_MANIFEST_CONFIG_KEY: str = "config"
DBT_MANIFEST_MATERIALIZED_KEY: str = "materialized"


DBT_DEFER_FLAG: str = "--defer"
DBT_FULL_REFRESH_FLAG: str = "--full-refresh"
DBT_UNIQUE_ID_SEPARATOR: str = "."
