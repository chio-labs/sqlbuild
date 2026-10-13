//! `event_exists_sql`: the lookup that makes an append-only event write idempotent.

use crate::events::_helpers::literals::quoted;

/// `SELECT event_id FROM <table> WHERE event_id = '<id>'`.
#[must_use]
pub fn event_exists_sql(table: &str, event_id: &str) -> String {
    format!(
        "SELECT event_id FROM {table} WHERE event_id = {}",
        quoted(event_id)
    )
}
