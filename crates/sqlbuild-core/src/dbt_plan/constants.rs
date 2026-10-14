//! dbt execution statuses and flags.

pub const SUCCESS_STATUSES: [&str; 6] = ["ok", "success", "pass", "passed", "warn", "warning"];
pub const WARN_STATUSES: [&str; 2] = ["warn", "warning"];
pub const FAIL_STATUSES: [&str; 3] = ["error", "fail", "failed"];
pub const SKIP_STATUSES: [&str; 2] = ["skip", "skipped"];
/// Resolved option flags that take a value and are rebuilt from options.
pub const RESOLVED_VALUE_FLAGS: [&str; 6] = [
    "--project-dir",
    "--profiles-dir",
    "--target",
    "--target-path",
    "--vars",
    "--state",
];
pub const DEFER_FLAG: &str = "--defer";
pub const SELECT_FLAG: &str = "--select";
/// Execution flags `dbt ls` does not accept.
pub const LS_EXCLUDED_FLAGS: [&str; 2] = ["--full-refresh", "--fail-fast"];
