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

DBT_EXECUTABLE_ENV_VAR: str = "DBT_EXECUTABLE"
DEFAULT_DBT_EXECUTABLE: str = "dbt"


DBT_DEFER_FLAG: str = "--defer"
DBT_EXECUTION_FAIL_STATUSES: frozenset[str] = frozenset({"error", "fail", "failed"})
DBT_EXECUTION_SKIP_STATUSES: frozenset[str] = frozenset({"skip", "skipped"})
DBT_EXECUTION_SUCCESS_STATUSES: frozenset[str] = frozenset(
    {"ok", "success", "pass", "passed", "warn", "warning"}
)
DBT_EXECUTION_WARN_STATUSES: frozenset[str] = frozenset({"warn", "warning"})
DBT_FULL_REFRESH_FLAG: str = "--full-refresh"
DBT_PATH_SELECTOR_SEPARATOR: str = "~"
DBT_SELECT_FLAG: str = "--select"
DBT_UNIQUE_ID_SEPARATOR: str = "."
