//! `event_cursor`: the opaque cursor of one durable event.

use crate::execution_history::_helpers::dialects::event_cursor_prefix;
use crate::execution_history::models::Dialect;

/// `<prefix><namespace>:<storage_id>`.
pub fn event_cursor(dialect: Dialect, namespace: &str, storage_id: i64) -> String {
    format!("{}{namespace}:{storage_id}", event_cursor_prefix(dialect))
}
