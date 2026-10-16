//! `read_scope_sql`: the ordered read of one scope's stored events.

use crate::microbatches::models::ScopeRead;

/// Every column of one scope's events, optionally one generation, by creation then event ID.
#[must_use]
pub fn read_scope_sql(table: &str, read: &ScopeRead<'_>) -> String {
    let generation: String = read
        .generation
        .map(|literal| format!("AND physical_generation_id = {literal} "))
        .unwrap_or_default();
    format!(
        "SELECT {} FROM {table} WHERE scope_kind = {} AND scope_key = {} {generation}\
ORDER BY created_at, event_id",
        read.columns.join(", "),
        read.scope_kind,
        read.scope_key
    )
}
