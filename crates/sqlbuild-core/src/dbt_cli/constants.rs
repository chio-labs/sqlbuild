//! dbt executable defaults, flags and routing error codes.

/// The dbt executable when no override is set.
pub const DEFAULT_DBT_EXECUTABLE: &str = "dbt";
/// SQLBuild-only flags `sqb dbt run` and `sqb dbt build` accept.
pub const EXECUTION_SQLBUILD_FLAGS: [&str; 7] = [
    "--start-cursor-ts",
    "--end-cursor-ts",
    "--start-cursor-int",
    "--end-cursor-int",
    "--defer-to",
    "--fail-fast",
    "--verbose",
];
/// SQLBuild-only flags `sqb dbt plan` accepts.
pub const PLAN_SQLBUILD_FLAGS: [&str; 5] = [
    "--start-cursor-ts",
    "--end-cursor-ts",
    "--start-cursor-int",
    "--end-cursor-int",
    "--defer-to",
];
pub const UNSUPPORTED_COMMAND_CODE: &str = "C236";
pub const EVENT_TIME_PAIR_CODE: &str = "C233";
pub const EVENT_TIME_CURSOR_CONFLICT_CODE: &str = "C234";
pub const SQLBUILD_FLAG_CODE: &str = "C232";
pub const EVENT_TIME_CURSOR_CONFLICT_HELP: &str =
    "Use dbt event-time flags or SQLBuild timestamp cursor overrides, not both.";
/// Help for a missing dbt project directory.
pub const MISSING_PROJECT_DIR_HELP: &str = "to point SQLBuild at the dbt project, set this in sqlbuild_project.toml:\n            [dbt]\n            project_dir = \"path/to/dbt_project\"\n  = help: or pass `--project-dir` to `sqb dbt`";
pub const MISSING_PROJECT_DIR_MESSAGE: &str = "dbt project directory is not configured";
pub(crate) const DBT_NO_CONNECTION_FLAG: &str = "--no-connection";
