//! rusqlite plumbing: error kinds, value conversion and transactions.

use rusqlite::types::{ToSqlOutput, Value, ValueRef};
use rusqlite::{Connection, ErrorCode};

use crate::records::models::RecallValue;
use crate::store::errors::{StoreError, StoreErrorKind};

/// The store error of a rusqlite failure, with what was being done.
pub(crate) fn store_error(error: &rusqlite::Error, doing: &str) -> StoreError {
    let kind = match error.sqlite_error_code() {
        Some(ErrorCode::ReadOnly | ErrorCode::CannotOpen | ErrorCode::PermissionDenied) => {
            StoreErrorKind::Permission
        }
        Some(ErrorCode::DatabaseBusy | ErrorCode::DatabaseLocked) => StoreErrorKind::Busy,
        Some(ErrorCode::NotADatabase | ErrorCode::DatabaseCorrupt) => StoreErrorKind::Corrupt,
        _ => StoreErrorKind::Other,
    };
    StoreError::new(kind, format!("{doing}: {error}"))
}

/// A closure's `rusqlite::Result` as a store result.
pub(crate) fn checked<T>(result: rusqlite::Result<T>, doing: &str) -> Result<T, StoreError> {
    result.map_err(|error| store_error(&error, doing))
}

pub(crate) fn to_sql(value: &RecallValue) -> ToSqlOutput<'_> {
    match value {
        RecallValue::Null => ToSqlOutput::Owned(Value::Null),
        RecallValue::Integer(number) => ToSqlOutput::Owned(Value::Integer(*number)),
        RecallValue::Real(number) => ToSqlOutput::Owned(Value::Real(*number)),
        RecallValue::Text(text) => ToSqlOutput::Borrowed(ValueRef::Text(text.as_bytes())),
        RecallValue::Blob(data) => ToSqlOutput::Borrowed(ValueRef::Blob(data)),
    }
}

pub(crate) fn from_sql(value: ValueRef<'_>) -> RecallValue {
    match value {
        ValueRef::Null => RecallValue::Null,
        ValueRef::Integer(number) => RecallValue::Integer(number),
        ValueRef::Real(number) => RecallValue::Real(number),
        ValueRef::Text(bytes) => RecallValue::Text(String::from_utf8_lossy(bytes).into_owned()),
        ValueRef::Blob(bytes) => RecallValue::Blob(bytes.to_vec()),
    }
}

/// Run `work` inside `BEGIN IMMEDIATE … COMMIT`, rolling back when it fails.
pub(crate) fn immediate<T>(
    connection: &Connection,
    doing: &str,
    work: impl FnOnce(&Connection) -> Result<T, StoreError>,
) -> Result<T, StoreError> {
    checked(connection.execute_batch("BEGIN IMMEDIATE"), doing)?;
    match work(connection) {
        Ok(value) => {
            if let Err(error) = connection.execute_batch("COMMIT") {
                drop(connection.execute_batch("ROLLBACK"));
                return Err(store_error(&error, doing));
            }
            Ok(value)
        }
        Err(error) => {
            drop(connection.execute_batch("ROLLBACK"));
            Err(error)
        }
    }
}

/// The highest schema version recorded in `recall_meta`, `None` before the first setup.
pub(crate) fn stored_schema_version(connection: &Connection) -> Result<Option<i64>, StoreError> {
    let exists: bool = checked(
        connection.query_row(
            "SELECT EXISTS (SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'recall_meta')",
            [],
            |row| row.get(0),
        ),
        "inspect Recall store",
    )?;
    if !exists {
        return Ok(None);
    }
    checked(
        connection.query_row(
            "SELECT MAX(CAST(value AS INTEGER)) FROM recall_meta \
             WHERE component = 'schema' AND key = 'schema_version'",
            [],
            |row| row.get(0),
        ),
        "read Recall schema version",
    )
}

/// A borrowed Recall value bound as a statement parameter.
pub(crate) struct SqlValue<'a>(pub(crate) &'a RecallValue);

impl rusqlite::ToSql for SqlValue<'_> {
    fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
        Ok(to_sql(self.0))
    }
}
