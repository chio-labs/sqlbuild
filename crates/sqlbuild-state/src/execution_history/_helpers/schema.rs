//! Schema version rejections.

use crate::execution_history::errors::{HistoryError, HistoryErrorKind};
use crate::execution_history::models::Dialect;

/// The rejection of an unsupported requested or stored schema version.
pub(crate) fn unsupported_version(dialect: Dialect, version: i64) -> HistoryError {
    let backend: &str = match dialect {
        Dialect::Sqlite => "SQLite",
        Dialect::Postgres => "PostgreSQL execution history",
    };
    HistoryError::new(
        HistoryErrorKind::UnsupportedSchemaVersion,
        format!("unsupported {backend} schema version {version}"),
    )
}
