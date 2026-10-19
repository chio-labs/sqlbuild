//! `checkpoint_sqlite_store`: copy the WAL into the store without waiting on anyone.

use crate::store::_helpers::sqlite::checked;
use crate::store::errors::StoreError;
use crate::store::models::SqliteStore;

/// A passive checkpoint: writers never checkpoint as they commit or close, so each session runs one when it starts, beside the command rather than after it.
pub fn checkpoint_sqlite_store(store: &SqliteStore) -> Result<(), StoreError> {
    checked(
        store
            .connection
            .query_row("PRAGMA wal_checkpoint(PASSIVE)", [], |_| Ok(())),
        "checkpoint Recall WAL",
    )
}
