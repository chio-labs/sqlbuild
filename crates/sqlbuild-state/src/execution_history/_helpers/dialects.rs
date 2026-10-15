//! Per-dialect placeholders, tables, cursor prefixes and parameter values.

use crate::execution_history::_helpers::timestamps::stored_text;
use crate::execution_history::constants::{
    POSTGRES_EVENT_CURSOR_PREFIX, POSTGRES_EVENT_TABLE, POSTGRES_PLACEHOLDER,
    POSTGRES_RUN_CURSOR_PREFIX, POSTGRES_RUN_TABLE, SQLITE_EVENT_CURSOR_PREFIX, SQLITE_EVENT_TABLE,
    SQLITE_PLACEHOLDER, SQLITE_RUN_CURSOR_PREFIX, SQLITE_RUN_TABLE,
};
use crate::execution_history::models::{Dialect, SqlParam};
use crate::execution_history::types::UtcTime;

/// The parameter placeholder.
pub(crate) fn placeholder(dialect: Dialect) -> &'static str {
    match dialect {
        Dialect::Sqlite => SQLITE_PLACEHOLDER,
        Dialect::Postgres => POSTGRES_PLACEHOLDER,
    }
}

/// The lifecycle event log table.
pub(crate) fn event_table(dialect: Dialect) -> &'static str {
    match dialect {
        Dialect::Sqlite => SQLITE_EVENT_TABLE,
        Dialect::Postgres => POSTGRES_EVENT_TABLE,
    }
}

/// The run projection table.
pub(crate) fn run_table(dialect: Dialect) -> &'static str {
    match dialect {
        Dialect::Sqlite => SQLITE_RUN_TABLE,
        Dialect::Postgres => POSTGRES_RUN_TABLE,
    }
}

/// The event cursor prefix.
pub(crate) fn event_cursor_prefix(dialect: Dialect) -> &'static str {
    match dialect {
        Dialect::Sqlite => SQLITE_EVENT_CURSOR_PREFIX,
        Dialect::Postgres => POSTGRES_EVENT_CURSOR_PREFIX,
    }
}

/// The run cursor prefix.
pub(crate) fn run_cursor_prefix(dialect: Dialect) -> &'static str {
    match dialect {
        Dialect::Sqlite => SQLITE_RUN_CURSOR_PREFIX,
        Dialect::Postgres => POSTGRES_RUN_CURSOR_PREFIX,
    }
}

/// A timestamp parameter: SQLite stores ISO text, PostgreSQL binds a `datetime`.
pub(crate) fn timestamp_param(dialect: Dialect, value: &UtcTime) -> SqlParam {
    match dialect {
        Dialect::Sqlite => SqlParam::Text(stored_text(value)),
        Dialect::Postgres => SqlParam::Timestamp(*value),
    }
}

/// An optional timestamp parameter.
pub(crate) fn optional_timestamp_param(dialect: Dialect, value: Option<&UtcTime>) -> SqlParam {
    value.map_or(SqlParam::Null, |value| timestamp_param(dialect, value))
}

/// An optional text parameter.
pub(crate) fn optional_text_param(value: Option<&String>) -> SqlParam {
    value.map_or(SqlParam::Null, |value| SqlParam::Text(value.clone()))
}
