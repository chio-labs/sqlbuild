//! `insert_rows`: write one batch atomically and idempotently.

use crate::records::models::RecallRow;
use crate::store::_helpers::rows::write_rows;
use crate::store::_helpers::sqlite::immediate;
use crate::store::errors::StoreError;
use crate::store::models::{InsertOutcome, SqliteStore};

/// Write `rows` in one transaction. A row whose key exists with equal content is a no-op; one with different content keeps the stored row and is reported and recorded as a conflict.
pub fn insert_rows(
    store: &SqliteStore,
    rows: &[RecallRow],
    ingested_at: &str,
) -> Result<InsertOutcome, StoreError> {
    immediate(&store.connection, "write Recall rows", |connection| {
        write_rows(connection, rows, ingested_at)
    })
}
