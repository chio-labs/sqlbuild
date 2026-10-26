//! `resolve_invocation`: the invocation an ID, unique prefix or `last` names.

use crate::store::_helpers::sqlite::checked;
use crate::store::constants::{LAST_INVOCATION_SELECTOR as LAST, LISTED_INVOCATION_CANDIDATES};
use crate::store::errors::StoreError;
use crate::store::main::chosen_invocation::chosen_invocation;
use crate::store::models::SqliteStore;

/// The full invocation ID of `selector`; `last` is the most recently started invocation.
pub fn resolve_invocation(store: &SqliteStore, selector: &str) -> Result<String, StoreError> {
    let candidates: Vec<String> = if selector == LAST {
        let mut statement = checked(
            store.connection.prepare(
                "SELECT invocation_id FROM invocations \
                 ORDER BY invocation_started_at DESC, invocation_id DESC LIMIT 1",
            ),
            "find the last invocation",
        )?;
        checked(
            statement
                .query_map([], |row| row.get(0))
                .and_then(Iterator::collect),
            "find the last invocation",
        )?
    } else {
        let mut statement = checked(
            store.connection.prepare(
                "SELECT invocation_id FROM invocations \
                 WHERE substr(invocation_id, 1, length(?1)) = ?1 \
                 ORDER BY invocation_id LIMIT ?2",
            ),
            "find the invocation",
        )?;
        checked(
            statement
                .query_map(
                    rusqlite::params![selector, LISTED_INVOCATION_CANDIDATES + 1],
                    |row| row.get(0),
                )
                .and_then(Iterator::collect),
            "find the invocation",
        )?
    };
    chosen_invocation(selector, &candidates)
}
