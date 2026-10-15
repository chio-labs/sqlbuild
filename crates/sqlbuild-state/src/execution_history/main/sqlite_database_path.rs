//! `sqlite_database_path`: where a SQLite history lives, once its settings are valid.

use sqlbuild_core::posix_path::main::posix_join::posix_join;
use sqlbuild_core::posix_path::main::posix_parts::posix_parts;

use crate::execution_history::constants::{
    MEMORY_PATH, MIN_TIMEOUT, SQLITE_DIRECTORY_NAME, SQLITE_FILE_NAME,
};
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::SqliteLocation;

/// `:memory:`, the normalised explicit path, or `<project>/.sqlbuild/history.sqlite3`; the busy timeout must be positive.
pub fn sqlite_database_path(location: &SqliteLocation) -> Result<String, HistoryError> {
    if location.project_dir.is_some() && location.path.is_some() {
        return Err(HistoryError::new(
            HistoryErrorKind::Storage,
            "provide project_dir or path, not both",
        ));
    }
    if location
        .busy_timeout_ms
        .is_none_or(|timeout| timeout < MIN_TIMEOUT)
    {
        return Err(HistoryError::new(
            HistoryErrorKind::Storage,
            "busy_timeout_ms must be a positive integer",
        ));
    }
    let selected: &str = location
        .path
        .as_deref()
        .or(location.project_dir.as_deref())
        .unwrap_or(&location.working_directory);
    if selected == MEMORY_PATH {
        return Ok(MEMORY_PATH.to_owned());
    }
    let mut parts: Vec<&str> = posix_parts(selected);
    if location.path.is_none() {
        parts.extend([SQLITE_DIRECTORY_NAME, SQLITE_FILE_NAME]);
    }
    Ok(posix_join(&parts))
}
