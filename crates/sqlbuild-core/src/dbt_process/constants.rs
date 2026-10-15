//! Environment and timing of dbt subprocesses.

use std::time::Duration;

/// Environment a JSON log stream adds to the inherited one.
pub const DBT_JSON_ENVIRONMENT: [(&str, &str); 2] =
    [("DBT_LOG_FORMAT", "json"), ("PYTHONUNBUFFERED", "1")];
/// Variables pointing dbt's artifacts and logs at the target folder.
pub const DBT_TARGET_PATH_VARIABLES: [&str; 2] = ["DBT_TARGET_PATH", "DBT_LOG_PATH"];
/// How long a stopping dbt process may take after each terminate or kill.
pub const DBT_STOP_WAIT: Duration = Duration::from_secs(1);
/// How often a stopping dbt process is polled.
pub(crate) const DBT_STOP_POLL: Duration = Duration::from_millis(10);
