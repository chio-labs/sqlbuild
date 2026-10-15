//! `schema_migration_needed`: whether a stored schema version still needs the current schema.

use crate::execution_history::_helpers::schema::unsupported_version;
use crate::execution_history::constants::NO_SCHEMA;
use crate::execution_history::constants::SCHEMA_VERSION;
use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::Dialect;

/// `false` at the current version, `true` below it, an error when newer or negative.
pub fn schema_migration_needed(dialect: Dialect, current: i64) -> Result<bool, HistoryError> {
    let backend: &str = match dialect {
        Dialect::Sqlite => "SQLite history",
        Dialect::Postgres => "PostgreSQL execution history",
    };
    if current > SCHEMA_VERSION {
        return Err(HistoryError::new(
            HistoryErrorKind::UnsupportedSchemaVersion,
            format!("{backend} schema {current} is newer than supported {SCHEMA_VERSION}"),
        ));
    }
    if current < NO_SCHEMA {
        return Err(unsupported_version(dialect, current));
    }
    Ok(current != SCHEMA_VERSION)
}
