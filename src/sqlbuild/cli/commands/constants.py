"""CLI command decision constants."""

DBT_JSON_OUTPUT_OPTION: str = "--json"
DBT_VERBOSE_OPTIONS: frozenset[str] = frozenset({"--verbose", "-v"})
DBT_CLI_OUTPUT_OPTIONS: frozenset[str] = frozenset({DBT_JSON_OUTPUT_OPTION, *DBT_VERBOSE_OPTIONS})
DBT_CLONE_ORIGIN_TARGET_NAME_ARGUMENT: str = "origin_target_name"
DBT_CLONE_INDEX_ARGUMENT: str = "index"
DBT_NO_CONNECTION_OPTION: str = "--no-connection"
DBT_SCENARIO_CAPTURE_SUBCOMMAND: str = "capture"
DBT_SCENARIO_TEST_SUBCOMMAND: str = "test"
RECONCILE_ATTACH_COMMAND: str = "attach"
STATE_CHECKPOINTS_COMMAND: str = "checkpoints"
